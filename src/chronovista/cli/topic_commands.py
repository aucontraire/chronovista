"""
Topic CLI commands for chronovista.

Commands for exploring topics, finding content by topics, and topic analytics.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.tree import Tree

from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.repositories.channel_repository import ChannelRepository
from chronovista.repositories.channel_topic_repository import ChannelTopicRepository
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_topic_repository import VideoTopicRepository
from chronovista.services.topic_analytics_service import TopicAnalyticsService

console = Console()


async def resolve_topic_identifier(
    session,
    topic_repo: TopicCategoryRepository,
    identifier: str,
) -> Optional[Any]:
    """
    Resolve a topic identifier (ID or name) to a topic object.

    Accepts either:
    - A topic ID (e.g., "10", "23")
    - A topic name (e.g., "Music", "Gaming")

    If the name matches multiple topics, prompts for disambiguation.

    Parameters
    ----------
    session : AsyncSession
        Database session
    topic_repo : TopicCategoryRepository
        Topic category repository
    identifier : str
        Topic ID or name to resolve

    Returns
    -------
    Optional[TopicCategoryDB]
        Resolved topic or None if not found/cancelled
    """
    # First, try exact ID match
    topic = await topic_repo.get(session, identifier)
    if topic:
        return topic

    # Try exact name match (case-insensitive)
    from sqlalchemy import select, func
    from chronovista.db.models import TopicCategory as TopicCategoryDB

    result = await session.execute(
        select(TopicCategoryDB).where(
            func.lower(TopicCategoryDB.category_name) == identifier.lower()
        )
    )
    matches = list(result.scalars().all())

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        # Disambiguation needed
        console.print(
            f"\n[yellow]Multiple topics match '{identifier}':[/yellow]\n"
        )
        for i, match in enumerate(matches, 1):
            parent_info = f" (parent: {match.parent_topic_id})" if match.parent_topic_id else " (root)"
            console.print(f"  {i}. [cyan]{match.category_name}[/cyan] - ID: {match.topic_id}{parent_info}")

        console.print()
        choice = Prompt.ask(
            "Select topic number (or 'q' to cancel)",
            choices=[str(i) for i in range(1, len(matches) + 1)] + ["q"],
            default="1",
        )

        if choice == "q":
            return None

        return matches[int(choice) - 1]

    # Try partial name match as fallback
    partial_matches = await topic_repo.find_by_name(session, identifier)
    if len(partial_matches) == 1:
        return partial_matches[0]

    if len(partial_matches) > 1:
        console.print(
            f"\n[yellow]Multiple topics partially match '{identifier}':[/yellow]\n"
        )
        # Limit to first 10 for readability
        display_matches = partial_matches[:10]
        for i, match in enumerate(display_matches, 1):
            parent_info = f" (parent: {match.parent_topic_id})" if match.parent_topic_id else " (root)"
            console.print(f"  {i}. [cyan]{match.category_name}[/cyan] - ID: {match.topic_id}{parent_info}")

        if len(partial_matches) > 10:
            console.print(f"  ... and {len(partial_matches) - 10} more")

        console.print()
        valid_choices = [str(i) for i in range(1, len(display_matches) + 1)] + ["q"]
        choice = Prompt.ask(
            "Select topic number (or 'q' to cancel)",
            choices=valid_choices,
            default="1",
        )

        if choice == "q":
            return None

        return display_matches[int(choice) - 1]

    return None


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
    topic: str = typer.Argument(..., help="Topic ID or name (e.g., '10' or 'Music')")
) -> None:
    """Show detailed information about a specific topic."""

    async def run_show() -> None:
        try:
            topic_repo = TopicCategoryRepository()
            async for session in db_manager.get_session(echo=False):
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)

                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Show topic details
                details = f"""[bold]Topic ID:[/bold] {resolved_topic.topic_id}
[bold]Category Name:[/bold] {resolved_topic.category_name}
[bold]Type:[/bold] {resolved_topic.topic_type}
[bold]Parent Topic:[/bold] {resolved_topic.parent_topic_id or 'None'}
[bold]Created:[/bold] {resolved_topic.created_at.strftime('%Y-%m-%d %H:%M:%S')}"""

                console.print(
                    Panel(
                        details,
                        title=f"Topic: {resolved_topic.category_name}",
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
    topic: str = typer.Argument(..., help="Topic ID or name (e.g., '10' or 'Music')"),
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
                # Resolve topic by ID or name
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)
                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Find channels with this topic
                channel_ids = await channel_topic_repo.find_channels_by_topics(
                    session, [resolved_topic.topic_id], match_all=False
                )

                if not channel_ids:
                    console.print(
                        Panel(
                            f"[yellow]No channels found for topic '{resolved_topic.category_name}'[/yellow]",
                            title="No Channels",
                            border_style="yellow",
                        )
                    )
                    return

                # Limit results
                limited_channel_ids = channel_ids[:limit]

                # Get channel details
                channels_table = Table(
                    title=f"Channels for Topic: {resolved_topic.category_name} (showing {len(limited_channel_ids)} of {len(channel_ids)})",
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
    topic: str = typer.Argument(..., help="Topic ID or name (e.g., '10' or 'Music')"),
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
                # Resolve topic by ID or name
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)
                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Find videos with this topic
                video_ids = await video_topic_repo.find_videos_by_topics(
                    session, [resolved_topic.topic_id], match_all=False
                )

                if not video_ids:
                    console.print(
                        Panel(
                            f"[yellow]No videos found for topic '{resolved_topic.category_name}'[/yellow]",
                            title="No Videos",
                            border_style="yellow",
                        )
                    )
                    return

                # Limit results
                limited_video_ids = video_ids[:limit]

                # Get video details
                videos_table = Table(
                    title=f"Videos for Topic: {resolved_topic.category_name} (showing {len(limited_video_ids)} of {len(video_ids)})",
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


@topic_app.command("popular")
def popular_topics(
    metric: str = typer.Option(
        "videos", "--metric", "-m", help="Ranking metric: videos, channels, combined"
    ),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of topics to show"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json"
    ),
) -> None:
    """Show most popular topics ranked by content volume."""

    async def run_popular() -> None:
        try:
            analytics_service = TopicAnalyticsService()

            # Validate metric parameter
            valid_metrics = ["videos", "channels", "combined"]
            if metric not in valid_metrics:
                console.print(
                    Panel(
                        f"[red]❌ Invalid metric '{metric}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_metrics)}\n"
                        f"[dim]Example: chronovista topics popular --metric videos[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(f"[blue]📊 Analyzing topic popularity by {metric}...[/blue]")

            # Get popular topics
            popular_topics_list = await analytics_service.get_popular_topics(
                metric=metric, limit=limit  # type: ignore
            )

            if not popular_topics_list:
                console.print(
                    Panel(
                        "[yellow]No topics found with associated content[/yellow]",
                        title="No Data",
                        border_style="yellow",
                    )
                )
                return

            if format == "json":
                import json

                # Convert to JSON-serializable format
                topics_data = []
                for topic in popular_topics_list:
                    topics_data.append(
                        {
                            "rank": topic.rank,
                            "topic_id": topic.topic_id,
                            "category_name": topic.category_name,
                            "video_count": topic.video_count,
                            "channel_count": topic.channel_count,
                            "total_content_count": topic.total_content_count,
                            "video_percentage": float(topic.video_percentage),
                            "channel_percentage": float(topic.channel_percentage),
                            "popularity_score": float(topic.popularity_score),
                        }
                    )

                console.print(json.dumps(topics_data, indent=2))
                return

            # Create rich table for display
            table = Table(
                title=f"🏆 Most Popular Topics by {metric.title()} (showing {len(popular_topics_list)} of {limit})",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Rank", style="bold cyan", width=6)
            table.add_column("Topic ID", style="yellow", width=10)
            table.add_column("Category", style="green", width=30)
            table.add_column("Videos", style="blue", justify="right", width=10)
            table.add_column("Channels", style="purple", justify="right", width=10)
            table.add_column("Score", style="red", justify="right", width=12)

            if metric == "videos":
                table.add_column("Video %", style="cyan", justify="right", width=10)
            elif metric == "channels":
                table.add_column("Channel %", style="cyan", justify="right", width=10)
            else:  # combined
                table.add_column("Combined %", style="cyan", justify="right", width=12)

            for topic in popular_topics_list:
                # Format score based on metric
                score_str = f"{topic.popularity_score:.1f}"

                # Format percentage based on metric
                if metric == "videos":
                    percentage_str = f"{topic.video_percentage:.1f}%"
                elif metric == "channels":
                    percentage_str = f"{topic.channel_percentage:.1f}%"
                else:  # combined
                    avg_pct = (topic.video_percentage + topic.channel_percentage) / 2
                    percentage_str = f"{avg_pct:.1f}%"

                row_data = [
                    f"#{topic.rank}",
                    topic.topic_id,
                    (
                        topic.category_name[:27] + "..."
                        if len(topic.category_name) > 30
                        else topic.category_name
                    ),
                    f"{topic.video_count:,}",
                    f"{topic.channel_count:,}",
                    score_str,
                    percentage_str,
                ]

                table.add_row(*row_data)

            console.print(table)

            # Show summary stats
            total_videos = sum(topic.video_count for topic in popular_topics_list)
            total_channels = sum(topic.channel_count for topic in popular_topics_list)

            console.print(
                f"\n[dim]📈 Summary: {total_videos:,} videos and {total_channels:,} channels across top {len(popular_topics_list)} topics[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error analyzing topic popularity: {str(e)}[/red]",
                    title="Analytics Error",
                    border_style="red",
                )
            )

    asyncio.run(run_popular())


@topic_app.command("related")
def related_topics(
    topic: str = typer.Argument(..., help="Topic ID or name (e.g., '10' or 'Music')"),
    min_confidence: float = typer.Option(
        0.1, "--min-confidence", "-c", help="Minimum confidence score (0.0-1.0)"
    ),
    limit: int = typer.Option(
        10, "--limit", "-l", help="Maximum number of related topics to show"
    ),
) -> None:
    """Show topics that are related to the given topic through shared content."""

    async def run_related() -> None:
        try:
            analytics_service = TopicAnalyticsService()
            topic_repo = TopicCategoryRepository()

            # Validate confidence parameter
            if not 0.0 <= min_confidence <= 1.0:
                console.print(
                    Panel(
                        f"[red]Invalid confidence score '{min_confidence}'. Must be between 0.0 and 1.0[/red]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            # Resolve topic by ID or name
            async for session in db_manager.get_session(echo=False):
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)
                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                topic_id = resolved_topic.topic_id
                topic_name = resolved_topic.category_name

            console.print(f"[blue]🔍 Finding topics related to {topic_name}...[/blue]")

            # Get topic relationships
            relationships = await analytics_service.get_topic_relationships(
                topic_id=topic_id, min_confidence=min_confidence, limit=limit
            )

            if not relationships.relationships:
                console.print(
                    Panel(
                        f"[yellow]No related topics found for '{topic_name}' with confidence >= {min_confidence}[/yellow]\n"
                        f"Try lowering the minimum confidence score or ensure the topic has associated content.",
                        title="No Related Topics",
                        border_style="yellow",
                    )
                )
                return

            # Display source topic info
            console.print(
                Panel(
                    f"[bold cyan]{relationships.source_category_name}[/bold cyan] (ID: {relationships.source_topic_id})\n"
                    f"📺 {relationships.total_videos:,} videos • 📢 {relationships.total_channels:,} channels",
                    title="Source Topic",
                    border_style="cyan",
                )
            )

            # Create relationships table
            table = Table(
                title=f"🔗 Related Topics (showing {len(relationships.relationships)} relationships)",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Rank", style="bold cyan", width=6)
            table.add_column("Topic ID", style="yellow", width=10)
            table.add_column("Category", style="green", width=25)
            table.add_column("Shared Videos", style="blue", justify="right", width=14)
            table.add_column(
                "Shared Channels", style="purple", justify="right", width=15
            )
            table.add_column("Confidence", style="red", justify="right", width=12)
            table.add_column("Relationship", style="cyan", width=12)

            for rank, relationship in enumerate(relationships.relationships, 1):
                confidence_pct = relationship.confidence_score * 100
                confidence_str = f"{confidence_pct:.1f}%"

                # Color code confidence levels
                if confidence_pct >= 50:
                    confidence_style = "[bold green]"
                elif confidence_pct >= 25:
                    confidence_style = "[bold yellow]"
                else:
                    confidence_style = "[dim]"

                row_data = [
                    f"#{rank}",
                    relationship.topic_id,
                    (
                        relationship.category_name[:22] + "..."
                        if len(relationship.category_name) > 25
                        else relationship.category_name
                    ),
                    f"{relationship.shared_videos:,}",
                    f"{relationship.shared_channels:,}",
                    f"{confidence_style}{confidence_str}[/]",
                    relationship.relationship_type.title(),
                ]

                table.add_row(*row_data)

            console.print(table)

            # Show summary stats
            total_shared_videos = sum(
                rel.shared_videos for rel in relationships.relationships
            )
            total_shared_channels = sum(
                rel.shared_channels for rel in relationships.relationships
            )
            avg_confidence = sum(
                rel.confidence_score for rel in relationships.relationships
            ) / len(relationships.relationships)

            console.print(
                f"\n[dim]📊 Analysis Summary:[/dim]\n"
                f"[dim]• Total shared videos: {total_shared_videos:,}[/dim]\n"
                f"[dim]• Total shared channels: {total_shared_channels:,}[/dim]\n"
                f"[dim]• Average confidence: {avg_confidence * 100:.1f}%[/dim]\n"
                f"[dim]• Analysis date: {relationships.analysis_date[:10]}[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error analyzing topic relationships: {str(e)}[/red]",
                    title="Analytics Error",
                    border_style="red",
                )
            )

    asyncio.run(run_related())


@topic_app.command("overlap")
def topic_overlap(
    topic1: str = typer.Argument(..., help="First topic ID or name (e.g., '10' or 'Music')"),
    topic2: str = typer.Argument(..., help="Second topic ID or name (e.g., '20' or 'Gaming')"),
) -> None:
    """Show content overlap between two topics."""

    async def run_overlap() -> None:
        try:
            analytics_service = TopicAnalyticsService()
            topic_repo = TopicCategoryRepository()

            # Resolve topics by ID or name
            async for session in db_manager.get_session(echo=False):
                resolved_topic1 = await resolve_topic_identifier(session, topic_repo, topic1)
                if not resolved_topic1:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic1}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                resolved_topic2 = await resolve_topic_identifier(session, topic_repo, topic2)
                if not resolved_topic2:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic2}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                topic1_id = resolved_topic1.topic_id
                topic2_id = resolved_topic2.topic_id
                topic1_name = resolved_topic1.category_name
                topic2_name = resolved_topic2.category_name

            # Validate that topics are different
            if topic1_id == topic2_id:
                console.print(
                    Panel(
                        "[red]Cannot compare a topic with itself. Please provide two different topics.[/red]",
                        title="Invalid Comparison",
                        border_style="red",
                    )
                )
                return

            console.print(
                f"[blue]🔍 Analyzing overlap between {topic1_name} and {topic2_name}...[/blue]"
            )

            # Get topic overlap analysis
            overlap = await analytics_service.calculate_topic_overlap(
                topic1_id=topic1_id, topic2_id=topic2_id
            )

            # Display topic information
            console.print(
                Panel(
                    f"[bold cyan]Topic 1:[/bold cyan] {overlap.topic1_name} (ID: {overlap.topic1_id})\n"
                    f"📺 {overlap.topic1_videos:,} videos • 📢 {overlap.topic1_channels:,} channels\n\n"
                    f"[bold cyan]Topic 2:[/bold cyan] {overlap.topic2_name} (ID: {overlap.topic2_id})\n"
                    f"📺 {overlap.topic2_videos:,} videos • 📢 {overlap.topic2_channels:,} channels",
                    title="Topic Comparison",
                    border_style="cyan",
                )
            )

            # Create overlap analysis table
            table = Table(
                title="📊 Content Overlap Analysis",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Content Type", style="bold cyan", width=15)
            table.add_column("Topic 1 Count", style="blue", justify="right", width=15)
            table.add_column("Topic 2 Count", style="green", justify="right", width=15)
            table.add_column("Shared Count", style="purple", justify="right", width=15)
            table.add_column("Overlap %", style="red", justify="right", width=12)

            # Add video overlap row
            table.add_row(
                "Videos",
                f"{overlap.topic1_videos:,}",
                f"{overlap.topic2_videos:,}",
                f"{overlap.shared_videos:,}",
                f"{overlap.video_overlap_percentage:.1f}%",
            )

            # Add channel overlap row
            table.add_row(
                "Channels",
                f"{overlap.topic1_channels:,}",
                f"{overlap.topic2_channels:,}",
                f"{overlap.shared_channels:,}",
                f"{overlap.channel_overlap_percentage:.1f}%",
            )

            console.print(table)

            # Display overall similarity metrics
            jaccard_pct = overlap.jaccard_similarity * 100

            # Color code overlap strength
            if overlap.overlap_strength == "strong":
                strength_style = "[bold green]"
            elif overlap.overlap_strength == "moderate":
                strength_style = "[bold yellow]"
            elif overlap.overlap_strength == "weak":
                strength_style = "[yellow]"
            else:
                strength_style = "[dim]"

            console.print(
                Panel(
                    f"[bold]Overall Similarity Metrics:[/bold]\n\n"
                    f"🎯 Jaccard Similarity: [bold cyan]{jaccard_pct:.2f}%[/bold cyan]\n"
                    f"📈 Overlap Strength: {strength_style}{overlap.overlap_strength.title()}[/]\n\n"
                    f"[dim]The Jaccard similarity measures how similar the two topics are based on their shared content.[/dim]",
                    title="Similarity Analysis",
                    border_style="magenta",
                )
            )

            # Provide interpretation
            if overlap.overlap_strength == "strong":
                interpretation = "These topics have significant content overlap and are closely related."
            elif overlap.overlap_strength == "moderate":
                interpretation = (
                    "These topics share some content and have moderate relationship."
                )
            elif overlap.overlap_strength == "weak":
                interpretation = (
                    "These topics have limited overlap but some shared content."
                )
            else:
                interpretation = "These topics have minimal or no shared content."

            console.print(f"\n[dim]💡 Interpretation: {interpretation}[/dim]")

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error analyzing topic overlap: {str(e)}[/red]",
                    title="Analytics Error",
                    border_style="red",
                )
            )

    asyncio.run(run_overlap())


@topic_app.command("similar")
def similar_topics(
    topic: str = typer.Argument(..., help="Topic ID or name (e.g., '10' or 'Music')"),
    min_similarity: float = typer.Option(
        0.5, "--min-similarity", "-s", help="Minimum similarity score (0.0-1.0)"
    ),
    limit: int = typer.Option(
        10, "--limit", "-l", help="Maximum number of similar topics to show"
    ),
) -> None:
    """Show topics that are similar to the given topic based on content patterns."""

    async def run_similar() -> None:
        try:
            analytics_service = TopicAnalyticsService()
            topic_repo = TopicCategoryRepository()

            # Validate similarity parameter
            if not 0.0 <= min_similarity <= 1.0:
                console.print(
                    Panel(
                        f"[red]Invalid similarity score '{min_similarity}'. Must be between 0.0 and 1.0[/red]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            # Resolve topic by ID or name
            async for session in db_manager.get_session(echo=False):
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)
                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                topic_id = resolved_topic.topic_id
                topic_name = resolved_topic.category_name

            console.print(f"[blue]🔍 Finding topics similar to {topic_name}...[/blue]")

            # Get similar topics
            similar_topics_list = await analytics_service.get_similar_topics(
                topic_id=topic_id, min_similarity=min_similarity, limit=limit
            )

            if not similar_topics_list:
                console.print(
                    Panel(
                        f"[yellow]No similar topics found for '{topic_name}' with similarity >= {min_similarity}[/yellow]\n"
                        f"Try lowering the minimum similarity score or ensure the topic has associated content.",
                        title="No Similar Topics",
                        border_style="yellow",
                    )
                )
                return

            # Display source topic info
            console.print(
                Panel(
                    f"[bold cyan]Source Topic:[/bold cyan] {topic_name} (ID: {topic_id})",
                    title="Finding Similar Topics",
                    border_style="cyan",
                )
            )

            # Create similarity table
            table = Table(
                title=f"🔗 Similar Topics (showing {len(similar_topics_list)} matches)",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Rank", style="bold cyan", width=6)
            table.add_column("Topic ID", style="yellow", width=10)
            table.add_column("Category", style="green", width=25)
            table.add_column("Videos", style="blue", justify="right", width=10)
            table.add_column("Channels", style="purple", justify="right", width=10)
            table.add_column("Similarity", style="red", justify="right", width=12)
            table.add_column("Pattern", style="cyan", width=15)

            for topic in similar_topics_list:
                similarity_pct = topic.popularity_score * 100
                similarity_str = f"{similarity_pct:.1f}%"

                # Color code similarity levels
                if similarity_pct >= 80:
                    similarity_style = "[bold green]"
                elif similarity_pct >= 60:
                    similarity_style = "[bold yellow]"
                else:
                    similarity_style = "[dim]"

                # Determine content pattern
                if topic.video_count > topic.channel_count * 3:
                    pattern = "Video-heavy"
                elif topic.channel_count > topic.video_count * 3:
                    pattern = "Channel-heavy"
                else:
                    pattern = "Balanced"

                row_data = [
                    f"#{topic.rank}",
                    topic.topic_id,
                    (
                        topic.category_name[:22] + "..."
                        if len(topic.category_name) > 25
                        else topic.category_name
                    ),
                    f"{topic.video_count:,}",
                    f"{topic.channel_count:,}",
                    f"{similarity_style}{similarity_str}[/]",
                    pattern,
                ]

                table.add_row(*row_data)

            console.print(table)

            # Show summary stats
            avg_similarity = sum(
                topic.popularity_score for topic in similar_topics_list
            ) / len(similar_topics_list)

            console.print(
                f"\n[dim]📊 Analysis Summary:[/dim]\n"
                f"[dim]• Average similarity: {avg_similarity * 100:.1f}%[/dim]\n"
                f"[dim]• Similarity algorithm: Content volume + ratio patterns[/dim]\n"
                f"[dim]• Found {len(similar_topics_list)} topics with >= {min_similarity * 100:.1f}% similarity[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error analyzing topic similarity: {str(e)}[/red]",
                    title="Analytics Error",
                    border_style="red",
                )
            )

    asyncio.run(run_similar())


@topic_app.command("export")
def export_topics(
    format: str = typer.Option(
        "csv", "--format", "-f", help="Export format: csv, json"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    include_videos: bool = typer.Option(
        True, "--include-videos", help="Include video-topic associations"
    ),
    include_channels: bool = typer.Option(
        True, "--include-channels", help="Include channel-topic associations"
    ),
) -> None:
    """Export topic data and associations to CSV or JSON format."""

    async def run_export() -> None:
        try:
            # Validate format
            valid_formats = ["csv", "json"]
            if format not in valid_formats:
                console.print(
                    Panel(
                        f"[red]❌ Invalid format '{format}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_formats)}\n"
                        f"[dim]Example: chronovista topics export --format csv[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(
                f"[blue]📤 Exporting topic data in {format.upper()} format...[/blue]"
            )

            # Generate output filename if not provided
            if output is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Ensure export directory exists
                settings.create_directories()
                output_path = (
                    settings.export_dir / f"chronovista_topics_{timestamp}.{format}"
                )
            else:
                output_path = Path(output)

            # Initialize repositories
            topic_repo = TopicCategoryRepository()
            video_topic_repo = VideoTopicRepository()
            channel_topic_repo = ChannelTopicRepository()
            video_repo = VideoRepository()
            channel_repo = ChannelRepository()

            async for session in db_manager.get_session(echo=False):
                export_data = {}

                # Export topic categories
                topics = await topic_repo.get_multi(session, skip=0, limit=1000)
                topic_data: List[Dict[str, Any]] = []
                for topic in topics:
                    topic_data.append(
                        {
                            "topic_id": topic.topic_id,
                            "category_name": topic.category_name,
                            "topic_type": topic.topic_type,
                            "parent_topic_id": topic.parent_topic_id,
                            "created_at": (
                                topic.created_at.isoformat()
                                if topic.created_at
                                else None
                            ),
                        }
                    )
                export_data["topic_categories"] = topic_data

                # Export video-topic associations if requested
                if include_videos:
                    video_topics = await video_topic_repo.get_multi(
                        session, skip=0, limit=10000
                    )
                    video_topic_data: List[Dict[str, Any]] = []

                    for vt in video_topics:
                        # Get video details for additional context
                        video = await video_repo.get_by_video_id(session, vt.video_id)
                        video_topic_data.append(
                            {
                                "video_id": vt.video_id,
                                "topic_id": vt.topic_id,
                                "relevance_type": vt.relevance_type,
                                "created_at": (
                                    vt.created_at.isoformat() if vt.created_at else None
                                ),
                                # Include video metadata for context
                                "video_title": video.title if video else None,
                                "video_channel_id": video.channel_id if video else None,
                                "video_upload_date": (
                                    video.upload_date.isoformat()
                                    if video and video.upload_date
                                    else None
                                ),
                            }
                        )
                    export_data["video_topics"] = video_topic_data
                    console.print(
                        f"[green]✅ Exported {len(video_topic_data)} video-topic associations[/green]"
                    )

                # Export channel-topic associations if requested
                if include_channels:
                    channel_topics = await channel_topic_repo.get_multi(
                        session, skip=0, limit=10000
                    )
                    channel_topic_data: List[Dict[str, Any]] = []

                    for ct in channel_topics:
                        # Get channel details for additional context
                        channel = await channel_repo.get_by_channel_id(
                            session, ct.channel_id
                        )
                        channel_topic_data.append(
                            {
                                "channel_id": ct.channel_id,
                                "topic_id": ct.topic_id,
                                "created_at": (
                                    ct.created_at.isoformat() if ct.created_at else None
                                ),
                                # Include channel metadata for context
                                "channel_title": channel.title if channel else None,
                                "channel_subscriber_count": (
                                    channel.subscriber_count if channel else None
                                ),
                            }
                        )
                    export_data["channel_topics"] = channel_topic_data
                    console.print(
                        f"[green]✅ Exported {len(channel_topic_data)} channel-topic associations[/green]"
                    )

                # Export based on format
                if format == "json":
                    # JSON export
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(export_data, f, indent=2, ensure_ascii=False)

                elif format == "csv":
                    # CSV export - create separate files for each data type
                    import csv

                    base_path = output_path.with_suffix("")

                    # Export topic categories
                    topics_csv_path = f"{base_path}_categories.csv"
                    with open(topics_csv_path, "w", newline="", encoding="utf-8") as f:
                        if topic_data:
                            writer = csv.DictWriter(f, fieldnames=topic_data[0].keys())
                            writer.writeheader()
                            writer.writerows(topic_data)

                    # Export video-topic associations
                    if include_videos and video_topic_data:
                        video_topics_csv_path = f"{base_path}_video_topics.csv"
                        with open(
                            video_topics_csv_path, "w", newline="", encoding="utf-8"
                        ) as f:
                            writer = csv.DictWriter(
                                f, fieldnames=video_topic_data[0].keys()
                            )
                            writer.writeheader()
                            writer.writerows(video_topic_data)

                    # Export channel-topic associations
                    if include_channels and channel_topic_data:
                        channel_topics_csv_path = f"{base_path}_channel_topics.csv"
                        with open(
                            channel_topics_csv_path, "w", newline="", encoding="utf-8"
                        ) as f:
                            writer = csv.DictWriter(
                                f, fieldnames=channel_topic_data[0].keys()
                            )
                            writer.writeheader()
                            writer.writerows(channel_topic_data)

                # Show export summary
                console.print(
                    Panel(
                        f"[bold green]✅ Export Complete![/bold green]\n\n"
                        f"📄 Format: {format.upper()}\n"
                        f"📁 Output: {output_path.absolute()}\n"
                        f"🏷️ Topics: {len(topic_data)} categories\n"
                        + (
                            f"📺 Video associations: {len(video_topic_data)}\n"
                            if include_videos
                            else ""
                        )
                        + (
                            f"📢 Channel associations: {len(channel_topic_data)}\n"
                            if include_channels
                            else ""
                        )
                        + f"\n[dim]Data includes topic metadata and association details for analysis.[/dim]",
                        title="Export Summary",
                        border_style="green",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error exporting topic data: {str(e)}[/red]",
                    title="Export Error",
                    border_style="red",
                )
            )

    asyncio.run(run_export())


@topic_app.command("graph")
def topic_graph_export(
    format: str = typer.Option(
        "dot", "--format", "-f", help="Export format: dot, json"
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (defaults to timestamped filename)",
    ),
    min_confidence: float = typer.Option(
        0.1,
        "--min-confidence",
        "-c",
        help="Minimum confidence score for relationships (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum number of topics to include in graph"
    ),
) -> None:
    """Export topic relationship graph for visualization tools."""

    async def run_graph_export() -> None:
        try:
            # Validate format
            valid_formats = ["dot", "json"]
            if format not in valid_formats:
                console.print(
                    Panel(
                        f"[red]❌ Invalid format '{format}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_formats)}\n"
                        f"[dim]Example: chronovista topics graph --format dot[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(
                Panel(
                    "[bold cyan]🕸️ Topic Relationship Graph Export[/bold cyan]\n\n"
                    f"Generating {format.upper()} graph with {limit} topics.\n"
                    f"Including relationships with ≥{min_confidence:.1f} confidence.",
                    title="Graph Export",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

            analytics_service = TopicAnalyticsService()

            # Generate appropriate timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                if format == "dot":
                    progress.add_task("Generating DOT graph...", total=None)
                    graph_content = await analytics_service.generate_topic_graph_dot(
                        min_confidence=min_confidence, max_topics=limit
                    )

                    # Determine output filename
                    if output:
                        output_path = Path(output)
                    else:
                        # Ensure export directory exists
                        settings.create_directories()
                        output_path = (
                            settings.export_dir / f"topic_graph_{timestamp}.dot"
                        )

                    # Write DOT file
                    output_path.write_text(graph_content, encoding="utf-8")

                    console.print(
                        Panel(
                            f"[bold green]✅ DOT Graph Export Complete![/bold green]\n\n"
                            f"📄 File: {output_path}\n"
                            f"🕸️ Topics: {limit}\n"
                            f"🔗 Min Confidence: {min_confidence:.1f}\n"
                            f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                            f"[bold yellow]💡 Visualization Tips:[/bold yellow]\n"
                            f"• Use Graphviz: [dim]dot -Tpng {output_path} -o graph.png[/dim]\n"
                            f"• Online viewer: [dim]https://dreampuf.github.io/GraphvizOnline/[/dim]\n"
                            f"• VS Code: Install Graphviz Preview extension",
                            title="Export Complete",
                            border_style="green",
                        )
                    )

                elif format == "json":
                    progress.add_task("Generating JSON graph...", total=None)
                    graph_data = await analytics_service.generate_topic_graph_json(
                        min_confidence=min_confidence, max_topics=limit
                    )

                    # Determine output filename
                    if output:
                        output_path = Path(output)
                    else:
                        # Ensure export directory exists
                        settings.create_directories()
                        output_path = (
                            settings.export_dir / f"topic_graph_{timestamp}.json"
                        )

                    # Write JSON file
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(graph_data, f, indent=2, ensure_ascii=False)

                    console.print(
                        Panel(
                            f"[bold green]✅ JSON Graph Export Complete![/bold green]\n\n"
                            f"📄 File: {output_path}\n"
                            f"🕸️ Nodes: {graph_data['metadata']['total_topics']}\n"
                            f"🔗 Links: {graph_data['metadata']['total_links']}\n"
                            f"⚖️ Min Confidence: {min_confidence:.1f}\n"
                            f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                            f"[bold yellow]💡 Visualization Tips:[/bold yellow]\n"
                            f"• D3.js Force Layout: Compatible format\n"
                            f"• NetworkX Python: [dim]import json; nx.from_dict_of_lists()[/dim]\n"
                            f"• Cytoscape: Convert nodes/links format\n"
                            f"• Observable: Upload to observablehq.com",
                            title="Export Complete",
                            border_style="green",
                        )
                    )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error generating graph: {str(e)}[/red]\n\n"
                    "[yellow]💡 Try:[/yellow]\n"
                    "• Check if topics exist: [dim]chronovista topics list[/dim]\n"
                    "• Reduce --limit or --min-confidence\n"
                    "• Ensure database contains topic relationships",
                    title="Graph Export Error",
                    border_style="red",
                )
            )

    asyncio.run(run_graph_export())


@topic_app.command("heatmap")
def topic_heatmap_export(
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    period: str = typer.Option(
        "monthly", "--period", "-p", help="Time period: monthly, weekly, daily"
    ),
    months_back: int = typer.Option(
        12,
        "--months-back",
        "-m",
        help="Number of months to look back (1-60)",
        min=1,
        max=60,
    ),
) -> None:
    """Generate topic activity heatmap data for visualization."""

    async def run_heatmap_export() -> None:
        try:
            # Validate period
            valid_periods = ["monthly", "weekly", "daily"]
            if period not in valid_periods:
                console.print(
                    Panel(
                        f"[red]❌ Invalid period '{period}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_periods)}\n"
                        f"[dim]Example: chronovista topics heatmap --period monthly[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(
                Panel(
                    "[bold orange1]🔥 Topic Activity Heatmap Export[/bold orange1]\n\n"
                    f"Generating {period} heatmap data for the last {months_back} months.\n"
                    "Creating time-series activity matrix for visualization.",
                    title="Heatmap Export",
                    border_style="orange1",
                    padding=(1, 2),
                )
            )

            analytics_service = TopicAnalyticsService()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Generating heatmap data...", total=None)

                # Get trends data for all topics
                trends = await analytics_service.get_topic_trends(
                    period=period, limit_topics=100, months_back=months_back
                )

                if not trends:
                    console.print(
                        Panel(
                            "[yellow]📊 No trend data found[/yellow]\n\n"
                            "Heatmap requires:\n"
                            "• Video upload dates in database\n"
                            "• User interaction timestamps\n"
                            "• Topic associations\n\n"
                            "Try: [dim]chronovista sync all[/dim]",
                            title="No Data",
                            border_style="yellow",
                        )
                    )
                    return

                # Create heatmap data structure
                heatmap_data: Dict[str, Any] = {
                    "metadata": {
                        "period": period,
                        "months_back": months_back,
                        "total_topics": len(trends),
                        "generated_at": datetime.now().isoformat(),
                        "data_type": "topic_activity_heatmap",
                    },
                    "topics": [],
                    "periods": [],
                    "matrix": [],
                }

                # Group trends by topic
                from collections import defaultdict

                topic_trends = defaultdict(list)
                all_periods = set()

                for trend in trends:
                    topic_trends[trend.topic_id].append(trend)
                    all_periods.add(trend.period)

                # Sort periods chronologically
                sorted_periods = sorted(list(all_periods))
                heatmap_data["periods"] = sorted_periods

                # Build topics list and matrix
                for topic_id, topic_trend_list in topic_trends.items():
                    if topic_trend_list:  # Should always be true
                        first_trend = topic_trend_list[0]
                        heatmap_data["topics"].append(
                            {
                                "id": topic_id,
                                "name": first_trend.category_name,
                            }
                        )

                        # Create activity row for this topic
                        activity_row = []
                        trend_by_period = {t.period: t for t in topic_trend_list}

                        for period_key in sorted_periods:
                            if period_key in trend_by_period:
                                trend = trend_by_period[period_key]
                                activity_score = trend.video_count + trend.channel_count
                            else:
                                activity_score = 0
                            activity_row.append(activity_score)

                        heatmap_data["matrix"].append(activity_row)

                # Determine output filename
                if output:
                    output_path = Path(output)
                else:
                    # Ensure export directory exists
                    settings.create_directories()
                    output_path = (
                        settings.export_dir / f"topic_heatmap_{period}_{timestamp}.json"
                    )

                # Write heatmap file
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(heatmap_data, f, indent=2, ensure_ascii=False)

                console.print(
                    Panel(
                        f"[bold green]✅ Heatmap Export Complete![/bold green]\n\n"
                        f"📄 File: {output_path}\n"
                        f"🏷️ Topics: {len(heatmap_data['topics'])}\n"
                        f"📅 Periods: {len(sorted_periods)} {period} periods\n"
                        f"📊 Data Points: {len(heatmap_data['topics']) * len(sorted_periods)}\n"
                        f"⌚ Time Range: {months_back} months\n\n"
                        f"[bold yellow]💡 Visualization Tips:[/bold yellow]\n"
                        f"• Python: [dim]seaborn.heatmap(data)[/dim]\n"
                        f"• JavaScript: [dim]D3.js heatmap, Chart.js matrix[/dim]\n"
                        f"• R: [dim]ggplot2 + geom_tile()[/dim]\n"
                        f"• Excel: Import JSON, create pivot heatmap",
                        title="Export Complete",
                        border_style="green",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error generating heatmap: {str(e)}[/red]\n\n"
                    "[yellow]💡 Try:[/yellow]\n"
                    "• Check topic trends: [dim]chronovista topics trends[/dim]\n"
                    "• Reduce months_back parameter\n"
                    "• Ensure database contains temporal data",
                    title="Heatmap Export Error",
                    border_style="red",
                )
            )

    asyncio.run(run_heatmap_export())


@topic_app.command("chart")
def topic_chart(
    metric: str = typer.Option(
        "videos", "--metric", "-m", help="Chart metric: videos, channels, combined"
    ),
    limit: int = typer.Option(
        15, "--limit", "-l", help="Maximum number of topics to show in chart"
    ),
    width: int = typer.Option(
        50, "--width", "-w", help="Maximum bar width (characters)"
    ),
) -> None:
    """Display topic popularity as ASCII bar charts."""

    async def run_chart() -> None:
        try:
            analytics_service = TopicAnalyticsService()

            # Validate metric parameter
            valid_metrics = ["videos", "channels", "combined"]
            if metric not in valid_metrics:
                console.print(
                    Panel(
                        f"[red]❌ Invalid metric '{metric}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_metrics)}\n"
                        f"[dim]Example: chronovista topics chart --metric videos[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(
                f"[blue]📊 Generating topic popularity chart by {metric}...[/blue]"
            )

            # Get popular topics
            popular_topics_list = await analytics_service.get_popular_topics(
                metric=metric, limit=limit  # type: ignore
            )

            if not popular_topics_list:
                console.print(
                    Panel(
                        "[yellow]No topics found with associated content[/yellow]",
                        title="No Data",
                        border_style="yellow",
                    )
                )
                return

            # Find the maximum value for scaling
            if metric == "videos":
                max_value = max(topic.video_count for topic in popular_topics_list)
                value_key = "video_count"
                unit = "videos"
            elif metric == "channels":
                max_value = max(topic.channel_count for topic in popular_topics_list)
                value_key = "channel_count"
                unit = "channels"
            else:  # combined
                max_value = max(
                    topic.total_content_count for topic in popular_topics_list
                )
                value_key = "total_content_count"
                unit = "items"

            if max_value == 0:
                console.print(
                    Panel(
                        "[yellow]No content found for the selected metric[/yellow]",
                        title="No Data",
                        border_style="yellow",
                    )
                )
                return

            # Display chart header
            console.print(
                Panel(
                    f"[bold cyan]Topic Popularity Chart - {metric.title()}[/bold cyan]\n"
                    f"Showing top {len(popular_topics_list)} topics by {unit} count",
                    title="📊 ASCII Bar Chart",
                    border_style="cyan",
                )
            )

            # Generate ASCII bars
            console.print()  # Add spacing

            for rank, topic in enumerate(popular_topics_list, 1):
                # Get the value for this metric
                if metric == "videos":
                    value = topic.video_count
                elif metric == "channels":
                    value = topic.channel_count
                else:  # combined
                    value = topic.total_content_count

                # Calculate bar length (proportional to max value)
                if max_value > 0:
                    bar_length = int((value / max_value) * width)
                else:
                    bar_length = 0

                # Create the bar using Unicode block characters for better visual effect
                full_blocks = bar_length
                bar = "█" * full_blocks

                # Color the bars based on rank
                if rank <= 3:
                    bar_color = "[bold green]"  # Top 3 in green
                elif rank <= 7:
                    bar_color = "[bold yellow]"  # 4-7 in yellow
                else:
                    bar_color = "[blue]"  # Rest in blue

                # Format the topic name (truncate if too long)
                topic_name = topic.category_name
                if len(topic_name) > 20:
                    topic_name = topic_name[:17] + "..."

                # Calculate percentage of max
                percentage = (value / max_value * 100) if max_value > 0 else 0

                # Display the bar with data
                console.print(
                    f"[bold cyan]{rank:2d}.[/bold cyan] "
                    f"[white]{topic_name:<20}[/white] "
                    f"{bar_color}{bar:<{width}}[/] "
                    f"[dim]{value:,} {unit} ({percentage:.1f}%)[/dim]"
                )

            # Add summary statistics
            total_content = sum(
                getattr(topic, value_key) for topic in popular_topics_list
            )
            avg_content = (
                total_content / len(popular_topics_list) if popular_topics_list else 0
            )

            console.print()
            console.print(
                Panel(
                    f"[bold]Chart Statistics:[/bold]\n\n"
                    f"📊 Total {unit}: [bold cyan]{total_content:,}[/bold cyan]\n"
                    f"📈 Average per topic: [bold yellow]{avg_content:.1f}[/bold yellow]\n"
                    f"🏆 Highest: [bold green]{max_value:,}[/bold green] ({popular_topics_list[0].category_name})\n"
                    f"📉 Lowest: [bold red]{getattr(popular_topics_list[-1], value_key):,}[/bold red] ({popular_topics_list[-1].category_name})\n\n"
                    f"[dim]Chart shows relative distribution of {unit} across topics[/dim]",
                    title="📈 Summary",
                    border_style="magenta",
                )
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error generating topic chart: {str(e)}[/red]",
                    title="Chart Error",
                    border_style="red",
                )
            )

    asyncio.run(run_chart())


async def show_full_hierarchy(
    topic_repo: TopicCategoryRepository, show_stats: bool
) -> None:
    """
    Display the full YouTube topic hierarchy as a tree.

    Shows the 7 parent categories (Music, Gaming, Sports, etc.) with their
    child topics nested underneath.
    """
    from rich.tree import Tree

    from chronovista.repositories.video_topic_repository import VideoTopicRepository

    async for session in db_manager.get_session(echo=False):
        # Get root (parent) topics
        parents = await topic_repo.get_root_topics(session)

        if not parents:
            console.print(
                Panel(
                    "[yellow]No topics found. Run 'chronovista seed topics' first.[/yellow]",
                    title="No Topics",
                    border_style="yellow",
                )
            )
            return

        # Get video counts per topic if showing stats
        topic_video_counts: dict[str, int] = {}
        video_topic_repo = VideoTopicRepository() if show_stats else None

        # Build the tree
        tree = Tree(
            "[bold cyan]🏷️ YouTube Topic Hierarchy[/bold cyan]",
            guide_style="dim",
        )

        # Sort parents by name
        parents.sort(key=lambda t: t.category_name)
        total_children = 0

        for parent in parents:
            # Get video count for parent
            if show_stats and video_topic_repo:
                parent_count = await video_topic_repo.get_topic_video_count(
                    session, parent.topic_id
                )
                topic_video_counts[parent.topic_id] = parent_count

            # Parent label with stats
            video_count = topic_video_counts.get(parent.topic_id, 0)
            parent_label = f"[bold]{parent.category_name}[/bold] [dim]({parent.topic_id})[/dim]"
            if show_stats and video_count > 0:
                parent_label += f" [green]📺 {video_count:,}[/green]"

            parent_branch = tree.add(parent_label)

            # Get and add children
            children = await topic_repo.get_children(session, parent.topic_id)
            children.sort(key=lambda t: t.category_name)
            total_children += len(children)

            for child in children:
                # Get video count for child
                if show_stats and video_topic_repo:
                    child_count = await video_topic_repo.get_topic_video_count(
                        session, child.topic_id
                    )
                    topic_video_counts[child.topic_id] = child_count

                video_count = topic_video_counts.get(child.topic_id, 0)
                child_label = f"{child.category_name} [dim]({child.topic_id})[/dim]"
                if show_stats and video_count > 0:
                    child_label += f" [green]📺 {video_count:,}[/green]"

                parent_branch.add(child_label)

        # Display
        console.print()
        console.print(
            Panel(
                tree,
                title="🌳 Topic Hierarchy",
                border_style="green",
                padding=(1, 2),
            )
        )

        # Summary
        console.print(
            f"\n[dim]📊 {len(parents)} parent topics, "
            f"{total_children} child topics, "
            f"{len(parents) + total_children} total[/dim]"
        )


@topic_app.command("tree")
def topic_tree(
    topic_id: Optional[str] = typer.Argument(
        None, help="Root topic ID to show relationships for (omit to show full hierarchy)"
    ),
    max_depth: int = typer.Option(
        3, "--max-depth", "-d", help="Maximum depth of relationship tree"
    ),
    min_confidence: float = typer.Option(
        0.1,
        "--min-confidence",
        "-c",
        help="Minimum confidence score for relationships (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    show_stats: bool = typer.Option(
        True, "--show-stats/--no-stats", help="Show content statistics for each topic"
    ),
) -> None:
    """Display topic hierarchy or relationships as a tree.

    When called without arguments, shows the full YouTube topic hierarchy.
    When a topic_id is provided, shows related topics based on co-occurrence.
    """

    async def run_tree() -> None:
        try:
            analytics_service = TopicAnalyticsService()
            topic_repo = TopicCategoryRepository()

            # If no topic_id provided, show the full hierarchy
            if topic_id is None:
                await show_full_hierarchy(topic_repo, show_stats)
                return

            # Validate confidence parameter
            if not 0.0 <= min_confidence <= 1.0:
                console.print(
                    Panel(
                        f"[red]Invalid confidence score '{min_confidence}'. Must be between 0.0 and 1.0[/red]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            console.print(
                f"[blue]🌳 Building topic relationship tree for {topic_id}...[/blue]"
            )

            # Get the root topic information
            async for session in db_manager.get_session(echo=False):
                root_topic = await topic_repo.get(session, topic_id)
                if not root_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic_id}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return
                break

            # Create the root of the tree
            # We already validated root_topic is not None above
            assert root_topic is not None

            if show_stats:
                # Get stats for root topic
                relationships = await analytics_service.get_topic_relationships(
                    topic_id=topic_id, min_confidence=0.0, limit=1
                )
                root_label = f"[bold cyan]{root_topic.category_name}[/bold cyan] (ID: {topic_id})"
                if relationships.total_videos > 0 or relationships.total_channels > 0:
                    root_label += f"\n  📺 {relationships.total_videos:,} videos • 📢 {relationships.total_channels:,} channels"
            else:
                root_label = f"[bold cyan]{root_topic.category_name}[/bold cyan] (ID: {topic_id})"

            tree = Tree(root_label)

            # Build the tree recursively
            await build_relationship_tree(
                tree=tree,
                topic_id=topic_id,
                analytics_service=analytics_service,
                topic_repo=topic_repo,
                visited_topics={topic_id},  # Track visited to prevent cycles
                current_depth=0,
                max_depth=max_depth,
                min_confidence=min_confidence,
                show_stats=show_stats,
            )

            # Display the tree
            console.print()
            console.print(
                Panel(
                    tree,
                    title="🌳 Topic Relationship Tree",
                    border_style="green",
                    padding=(1, 2),
                )
            )

            # Show tree statistics
            total_relationships = count_tree_nodes(tree) - 1  # Subtract root node
            console.print(
                f"\n[dim]📊 Tree Statistics:[/dim]\n"
                f"[dim]• Root topic: {root_topic.category_name}[/dim]\n"
                f"[dim]• Related topics found: {total_relationships}[/dim]\n"
                f"[dim]• Maximum depth: {max_depth}[/dim]\n"
                f"[dim]• Minimum confidence: {min_confidence * 100:.1f}%[/dim]\n"
                f"[dim]• Tree prevents cycles by tracking visited topics[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error building topic tree: {str(e)}[/red]",
                    title="Tree Error",
                    border_style="red",
                )
            )

    asyncio.run(run_tree())


async def build_relationship_tree(
    tree: Tree,
    topic_id: str,
    analytics_service: TopicAnalyticsService,
    topic_repo: TopicCategoryRepository,
    visited_topics: set[str],
    current_depth: int,
    max_depth: int,
    min_confidence: float,
    show_stats: bool,
) -> None:
    """
    Recursively build the relationship tree.

    Parameters
    ----------
    tree : Tree
        The Rich Tree node to add children to
    topic_id : str
        Current topic ID to find relationships for
    analytics_service : TopicAnalyticsService
        Service for getting topic relationships
    topic_repo : TopicCategoryRepository
        Repository for topic information
    visited_topics : set[str]
        Set of already visited topic IDs to prevent cycles
    current_depth : int
        Current depth in the tree
    max_depth : int
        Maximum allowed depth
    min_confidence : float
        Minimum confidence score for relationships
    show_stats : bool
        Whether to show content statistics
    """
    # Check depth limit
    if current_depth >= max_depth:
        return

    # Get relationships for current topic
    relationships = await analytics_service.get_topic_relationships(
        topic_id=topic_id,
        min_confidence=min_confidence,
        limit=10,  # Limit to prevent too many branches
    )

    # Add each related topic as a branch
    for relationship in relationships.relationships:
        related_topic_id = relationship.topic_id

        # Skip if we've already visited this topic (prevent cycles)
        if related_topic_id in visited_topics:
            continue

        # Create label for this relationship
        confidence_pct = relationship.confidence_score * 100

        # Color code based on confidence level
        if confidence_pct >= 50:
            confidence_color = "[bold green]"
        elif confidence_pct >= 25:
            confidence_color = "[bold yellow]"
        else:
            confidence_color = "[dim]"

        # Build the node label
        node_label = f"{confidence_color}{relationship.category_name}[/] (ID: {related_topic_id})"

        if show_stats:
            node_label += f"\n  🔗 {relationship.shared_videos:,} shared videos"
            if relationship.shared_channels > 0:
                node_label += f" • {relationship.shared_channels:,} shared channels"
            node_label += f" • {confidence_color}{confidence_pct:.1f}% confidence[/]"

        # Add this relationship as a branch
        branch = tree.add(node_label)

        # Mark this topic as visited and recurse
        visited_topics.add(related_topic_id)

        # Recursively build subtree for this relationship
        await build_relationship_tree(
            tree=branch,
            topic_id=related_topic_id,
            analytics_service=analytics_service,
            topic_repo=topic_repo,
            visited_topics=visited_topics.copy(),  # Use copy to allow different branches
            current_depth=current_depth + 1,
            max_depth=max_depth,
            min_confidence=min_confidence,
            show_stats=show_stats,
        )


def count_tree_nodes(tree: Tree) -> int:
    """
    Count the total number of nodes in a Rich Tree.

    Parameters
    ----------
    tree : Tree
        The Rich Tree to count nodes in

    Returns
    -------
    int
        Total number of nodes in the tree
    """
    count = 1  # Count this node
    for child in tree.children:
        count += count_tree_nodes(child)
    return count


@topic_app.command("explore")
def interactive_topic_exploration(
    show_analytics: bool = typer.Option(
        True, "--analytics/--no-analytics", help="Show analytics for selected topics"
    ),
    auto_advance: bool = typer.Option(
        False, "--auto-advance", help="Automatically proceed through topics"
    ),
) -> None:
    """Interactive topic selection and exploration with progress bars."""

    async def run_interactive() -> None:
        try:
            console.print(
                Panel(
                    "[bold cyan]🔍 Interactive Topic Explorer[/bold cyan]\n\n"
                    "Discover and analyze topics through an interactive interface.\n"
                    "Browse topics, view analytics, and explore relationships!",
                    title="Welcome to Topic Explorer",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

            topic_repo = TopicCategoryRepository()
            analytics_service = TopicAnalyticsService()

            # Phase 1: Load all topics with progress bar
            console.print("\n[blue]📊 Loading topic data...[/blue]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                load_task = progress.add_task(
                    "Loading topics from database...", total=100
                )

                async for session in db_manager.get_session(echo=False):
                    # Get all topics
                    progress.update(
                        load_task,
                        advance=25,
                        description="Fetching topic categories...",
                    )
                    topics = await topic_repo.get_multi(session, skip=0, limit=100)

                    progress.update(
                        load_task, advance=25, description="Loading topic analytics..."
                    )
                    if show_analytics:
                        popular_topics = await analytics_service.get_popular_topics(
                            metric="combined", limit=len(topics)
                        )
                        # Create a lookup for analytics data
                        analytics_lookup = {t.topic_id: t for t in popular_topics}
                    else:
                        analytics_lookup = {}

                    progress.update(
                        load_task,
                        advance=25,
                        description="Processing topic relationships...",
                    )
                    # Simulate some processing time for realistic progress
                    import asyncio

                    await asyncio.sleep(0.5)

                    progress.update(
                        load_task, advance=25, description="Ready for exploration!"
                    )
                    await asyncio.sleep(0.3)
                    break

            if not topics:
                console.print(
                    Panel(
                        "[yellow]No topics found in database[/yellow]\n"
                        "Use 'chronovista sync topics' to populate topic data first.",
                        title="No Topics Available",
                        border_style="yellow",
                    )
                )
                return

            # Phase 2: Interactive topic selection loop
            console.print(
                f"\n[green]✅ Loaded {len(topics)} topics successfully![/green]"
            )

            selected_topics: List[Any] = []
            continue_exploring = True

            while continue_exploring:
                # Display topic selection menu
                console.print("\n" + "=" * 60)
                console.print("[bold cyan]📋 Available Topics[/bold cyan]")
                console.print("=" * 60)

                # Create a paginated topic table
                topic_table = Table(
                    title=f"Topic Categories ({len(topics)} available)",
                    show_header=True,
                    header_style="bold magenta",
                )
                topic_table.add_column("Index", style="cyan", width=6)
                topic_table.add_column("Topic ID", style="yellow", width=10)
                topic_table.add_column("Category Name", style="green", width=25)

                if show_analytics and analytics_lookup:
                    topic_table.add_column(
                        "Videos", style="blue", justify="right", width=8
                    )
                    topic_table.add_column(
                        "Channels", style="purple", justify="right", width=10
                    )
                    topic_table.add_column(
                        "Score", style="red", justify="right", width=8
                    )

                # Show first 20 topics for selection
                display_topics = topics[:20]
                for idx, topic in enumerate(display_topics, 1):
                    row_data = [
                        str(idx),
                        topic.topic_id,
                        (
                            topic.category_name[:22] + "..."
                            if len(topic.category_name) > 25
                            else topic.category_name
                        ),
                    ]

                    if show_analytics and topic.topic_id in analytics_lookup:
                        analytics = analytics_lookup[topic.topic_id]
                        row_data.extend(
                            [
                                f"{analytics.video_count:,}",
                                f"{analytics.channel_count:,}",
                                f"{analytics.popularity_score:.1f}",
                            ]
                        )
                    elif show_analytics:
                        row_data.extend(["0", "0", "0.0"])

                    topic_table.add_row(*row_data)

                console.print(topic_table)

                # Interactive topic selection
                console.print(
                    f"\n[dim]Selected topics: {len(selected_topics)} | Commands: 'help', 'done', 'clear', 'show'[/dim]"
                )

                if auto_advance and not selected_topics:
                    # Auto-select the first few popular topics
                    user_input = "1,2,3"
                    console.print(
                        f"[dim]Auto-advance mode: selecting topics {user_input}[/dim]"
                    )
                else:
                    user_input = Prompt.ask(
                        "\n[bold]Select topic(s)[/bold]",
                        default="help",
                        show_default=True,
                    )

                # Process user input
                if user_input.lower() == "help":
                    console.print(
                        Panel(
                            "[bold]Interactive Topic Explorer Commands:[/bold]\n\n"
                            "• [cyan]1,2,3[/cyan] - Select topics by index (comma-separated)\n"
                            "• [cyan]show[/cyan] - Display detailed analysis of selected topics\n"
                            "• [cyan]clear[/cyan] - Clear all selected topics\n"
                            "• [cyan]done[/cyan] - Finish selection and exit\n"
                            "• [cyan]help[/cyan] - Show this help message\n\n"
                            "[dim]Example: Type '1,5,10' to select topics at positions 1, 5, and 10[/dim]",
                            title="Help",
                            border_style="blue",
                        )
                    )
                    continue

                elif user_input.lower() == "done":
                    continue_exploring = False

                elif user_input.lower() == "clear":
                    selected_topics.clear()
                    console.print("[yellow]🗑️ Cleared all selected topics[/yellow]")
                    continue

                elif user_input.lower() == "show":
                    if not selected_topics:
                        console.print("[yellow]⚠️ No topics selected yet[/yellow]")
                        continue

                    # Show detailed analysis with progress bar
                    await show_selected_topics_analysis(
                        selected_topics,
                        analytics_service,
                        topic_repo,
                        console,
                        show_analytics,
                    )
                    continue

                else:
                    # Parse topic selection (numbers)
                    try:
                        indices = [
                            int(x.strip()) for x in user_input.split(",") if x.strip()
                        ]
                        valid_indices = [
                            i for i in indices if 1 <= i <= len(display_topics)
                        ]

                        if valid_indices:
                            newly_selected = [
                                display_topics[i - 1] for i in valid_indices
                            ]
                            # Add to selected topics (avoid duplicates)
                            for topic in newly_selected:
                                if topic not in selected_topics:
                                    selected_topics.append(topic)

                            console.print(
                                f"[green]✅ Added {len(newly_selected)} topic(s) to selection[/green]"
                            )

                            # Show brief summary of selected topics
                            if selected_topics:
                                summary = ", ".join(
                                    [f"{t.category_name}" for t in selected_topics[-3:]]
                                )
                                if len(selected_topics) > 3:
                                    summary = f"...{summary} (and {len(selected_topics)-3} more)"
                                console.print(
                                    f"[dim]Current selection: {summary}[/dim]"
                                )

                            # If auto-advance mode, automatically proceed to done
                            if auto_advance:
                                console.print(
                                    f"[dim]Auto-advance mode: proceeding to analysis...[/dim]"
                                )
                                continue_exploring = False
                        else:
                            console.print(
                                "[red]❌ Invalid selection. Please use numbers from the table above.[/red]"
                            )

                    except ValueError:
                        console.print(
                            "[red]❌ Invalid input. Use comma-separated numbers or commands (help, done, clear, show).[/red]"
                        )

            # Phase 3: Final analysis of selected topics
            if selected_topics:
                console.print(
                    f"\n[bold green]🎉 Topic exploration complete![/bold green]"
                )
                console.print(
                    f"[green]Selected {len(selected_topics)} topics for analysis[/green]"
                )

                # Final detailed analysis
                await show_selected_topics_analysis(
                    selected_topics,
                    analytics_service,
                    topic_repo,
                    console,
                    show_analytics,
                )

                # Ask if user wants to export results
                if Confirm.ask(
                    "\n[bold]Would you like to export these topics to a file?[/bold]",
                    default=False,
                ):
                    await export_selected_topics(selected_topics, console)
            else:
                console.print("\n[yellow]👋 No topics selected. Goodbye![/yellow]")

        except KeyboardInterrupt:
            console.print(
                "\n\n[yellow]👋 Interactive exploration cancelled by user[/yellow]"
            )
        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error during interactive exploration: {str(e)}[/red]",
                    title="Exploration Error",
                    border_style="red",
                )
            )

    asyncio.run(run_interactive())


@topic_app.command("discovery")
def topic_discovery_analysis(
    limit: int = typer.Option(
        15, "--limit", "-l", help="Number of top entry/retention topics to show"
    ),
    min_interactions: int = typer.Option(
        2,
        "--min-interactions",
        "-m",
        help="Minimum interactions to be considered active",
    ),
    discovery_method: Optional[str] = typer.Option(
        None,
        "--method",
        help="Filter by discovery method: liked_content, watched_complete, watched_partial, browsed",
    ),
) -> None:
    """Analyze how users discover topics based on viewing patterns."""

    async def run_discovery() -> None:
        try:
            console.print(
                Panel(
                    "[bold magenta]🔍 Topic Discovery Analytics[/bold magenta]\n\n"
                    "Analyze how users discover and engage with different topics.\n"
                    "Understand discovery patterns, entry points, and retention rates!",
                    title="Discovery Analytics",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )

            analytics_service = TopicAnalyticsService()

            # Run discovery analysis with progress indicator
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Analyzing user discovery patterns...", total=None)
                analysis = await analytics_service.get_topic_discovery_analysis(
                    limit_topics=limit, min_interactions=min_interactions
                )

            if analysis.total_users == 0:
                console.print(
                    Panel(
                        "[yellow]📊 No user interaction data found[/yellow]\n\n"
                        "Discovery analytics requires:\n"
                        "• User watch history data\n"
                        "• Video-topic associations\n"
                        "• User interaction tracking\n\n"
                        "Try running [cyan]chronovista sync history[/cyan] first to import watch data.",
                        title="Insufficient Data",
                        border_style="yellow",
                    )
                )
                return

            # Display overall summary
            console.print(f"\n[bold]📊 Discovery Overview[/bold]")

            summary_table = Table(show_header=True, header_style="bold cyan")
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", style="bold white", justify="right")

            summary_table.add_row("Total Users Analyzed", f"{analysis.total_users:,}")
            summary_table.add_row(
                "Total Discovery Events", f"{analysis.total_discoveries:,}"
            )
            avg_discoveries = analysis.total_discoveries / max(analysis.total_users, 1)
            summary_table.add_row("Avg Discoveries per User", f"{avg_discoveries:.1f}")

            console.print(summary_table)

            # Display discovery paths
            if analysis.discovery_paths:
                console.print(f"\n[bold]🛤️ Discovery Methods[/bold]")

                # Filter by discovery method if specified
                paths_to_show = analysis.discovery_paths
                if discovery_method:
                    paths_to_show = [
                        p
                        for p in paths_to_show
                        if p.discovery_method == discovery_method
                    ]
                    if not paths_to_show:
                        console.print(
                            f"[yellow]No data found for discovery method: {discovery_method}[/yellow]"
                        )
                        console.print(
                            f"Available methods: {', '.join(set(p.discovery_method for p in analysis.discovery_paths))}"
                        )
                        return

                paths_table = Table(show_header=True, header_style="bold green")
                paths_table.add_column("Method", style="green")
                paths_table.add_column("Topic", style="white")
                paths_table.add_column(
                    "Discoveries", style="bold white", justify="right"
                )
                paths_table.add_column("Avg Engagement", style="cyan", justify="right")
                paths_table.add_column(
                    "Retention Rate", style="yellow", justify="right"
                )

                for path in paths_to_show[:20]:  # Show top 20
                    method_emoji = {
                        "liked_content": "❤️",
                        "watched_complete": "✅",
                        "watched_partial": "⏯️",
                        "browsed": "👀",
                    }.get(path.discovery_method, "📝")

                    engagement_color = (
                        "green"
                        if path.avg_engagement >= 70
                        else "yellow" if path.avg_engagement >= 40 else "red"
                    )
                    retention_color = (
                        "green"
                        if path.retention_rate >= 60
                        else "yellow" if path.retention_rate >= 30 else "red"
                    )

                    paths_table.add_row(
                        f"{method_emoji} {path.discovery_method.replace('_', ' ').title()}",
                        path.category_name,
                        f"{path.discovery_count:,}",
                        f"[{engagement_color}]{path.avg_engagement:.1f}%[/{engagement_color}]",
                        f"[{retention_color}]{path.retention_rate:.1f}%[/{retention_color}]",
                    )

                console.print(paths_table)

            # Display top entry topics
            if analysis.top_entry_topics:
                console.print(f"\n[bold]🚪 Top Entry Topics[/bold]")
                console.print(
                    "[dim]Topics users discover first when starting their journey[/dim]"
                )

                entry_table = Table(show_header=True, header_style="bold blue")
                entry_table.add_column("Rank", style="dim", justify="center", width=6)
                entry_table.add_column("Topic", style="blue")
                entry_table.add_column(
                    "First Discoveries", style="bold white", justify="right"
                )
                entry_table.add_column("Entry Rate", style="cyan", justify="right")

                for topic in analysis.top_entry_topics:
                    rank_style = "gold1" if topic.rank <= 3 else "white"
                    rank_emoji = (
                        "🥇"
                        if topic.rank == 1
                        else (
                            "🥈"
                            if topic.rank == 2
                            else "🥉" if topic.rank == 3 else f"#{topic.rank}"
                        )
                    )

                    entry_table.add_row(
                        f"[{rank_style}]{rank_emoji}[/{rank_style}]",
                        topic.category_name,
                        f"{topic.video_count:,}",
                        f"{topic.video_percentage:.1f}%",
                    )

                console.print(entry_table)

            # Display high retention topics
            if analysis.high_retention_topics:
                console.print(f"\n[bold]🎯 High Retention Topics[/bold]")
                console.print("[dim]Topics that keep users engaged long-term[/dim]")

                retention_table = Table(show_header=True, header_style="bold purple")
                retention_table.add_column(
                    "Rank", style="dim", justify="center", width=6
                )
                retention_table.add_column("Topic", style="purple")
                retention_table.add_column(
                    "Active Users", style="bold white", justify="right"
                )
                retention_table.add_column(
                    "Retention Rate", style="yellow", justify="right"
                )

                for topic in analysis.high_retention_topics:
                    rank_style = "gold1" if topic.rank <= 3 else "white"
                    rank_emoji = (
                        "🏆"
                        if topic.rank == 1
                        else (
                            "⭐"
                            if topic.rank == 2
                            else "🌟" if topic.rank == 3 else f"#{topic.rank}"
                        )
                    )

                    retention_color = (
                        "green"
                        if topic.popularity_score >= 80
                        else "yellow" if topic.popularity_score >= 60 else "red"
                    )

                    retention_table.add_row(
                        f"[{rank_style}]{rank_emoji}[/{rank_style}]",
                        topic.category_name,
                        f"{topic.video_count:,}",
                        f"[{retention_color}]{topic.popularity_score:.1f}%[/{retention_color}]",
                    )

                console.print(retention_table)

            # Show analysis metadata
            console.print(
                f"\n[dim]Analysis completed on {analysis.analysis_date[:19].replace('T', ' ')}[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error during discovery analysis: {e}[/red]",
                    title="Analysis Error",
                    border_style="red",
                )
            )

    asyncio.run(run_discovery())


@topic_app.command("trends")
def topic_trends_analysis(
    period: str = typer.Option(
        "monthly", "--period", "-p", help="Time period: monthly, weekly, daily"
    ),
    limit: int = typer.Option(
        15, "--limit", "-l", help="Number of topics to analyze trends for"
    ),
    months_back: int = typer.Option(
        12,
        "--months-back",
        "-m",
        help="Number of months to look back (1-60)",
        min=1,
        max=60,
    ),
    trend_direction: Optional[str] = typer.Option(
        None,
        "--direction",
        "-d",
        help="Filter by trend direction: growing, declining, stable",
    ),
) -> None:
    """Analyze topic popularity trends over time."""

    async def run_trends() -> None:
        try:
            console.print(
                Panel(
                    "[bold blue]📈 Topic Trends Analytics[/bold blue]\n\n"
                    "Analyze how topic popularity changes over time.\n"
                    "Discover growing trends, declining topics, and seasonal patterns!",
                    title="Trends Analytics",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

            # Validate period parameter
            valid_periods = ["monthly", "weekly", "daily"]
            if period not in valid_periods:
                console.print(
                    Panel(
                        f"[red]❌ Invalid period '{period}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_periods)}\n"
                        f"[dim]Example: chronovista topics trends --period monthly[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            # Validate trend direction if specified
            if trend_direction:
                valid_directions = ["growing", "declining", "stable"]
                if trend_direction not in valid_directions:
                    console.print(
                        Panel(
                            f"[red]❌ Invalid trend direction '{trend_direction}'.[/red]\n"
                            f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_directions)}\n"
                            f"[dim]Example: chronovista topics trends --filter growing[/dim]",
                            title="Invalid Parameter",
                            border_style="red",
                        )
                    )
                    return

            analytics_service = TopicAnalyticsService()

            # Run trends analysis with progress indicator
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(
                    f"Analyzing {period} trends over {months_back} months...",
                    total=None,
                )
                trends = await analytics_service.get_topic_trends(
                    period=period, limit_topics=limit, months_back=months_back
                )

            if not trends:
                console.print(
                    Panel(
                        "[yellow]📊 No trend data found[/yellow]\n\n"
                        "Trend analysis requires:\n"
                        "• Historical video upload data\n"
                        "• User interaction history\n"
                        "• Video-topic associations over time\n\n"
                        "Try running [cyan]chronovista sync history[/cyan] and [cyan]chronovista sync liked[/cyan] first.",
                        title="Insufficient Data",
                        border_style="yellow",
                    )
                )
                return

            # Filter by trend direction if specified
            if trend_direction:
                trends = [t for t in trends if t.trend_direction == trend_direction]
                if not trends:
                    console.print(
                        f"[yellow]No topics found with '{trend_direction}' trend direction[/yellow]"
                    )
                    return

            # Display overall summary
            console.print(
                f"\n[bold]📊 Trends Overview ({period.title()} Analysis)[/bold]"
            )

            summary_table = Table(show_header=True, header_style="bold cyan")
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", style="bold white", justify="right")

            growing_count = len([t for t in trends if t.trend_direction == "growing"])
            declining_count = len(
                [t for t in trends if t.trend_direction == "declining"]
            )
            stable_count = len([t for t in trends if t.trend_direction == "stable"])

            summary_table.add_row("Total Topics Analyzed", f"{len(trends):,}")
            summary_table.add_row(
                "Growing Topics", f"[bold green]{growing_count}[/bold green]"
            )
            summary_table.add_row(
                "Declining Topics", f"[bold red]{declining_count}[/bold red]"
            )
            summary_table.add_row(
                "Stable Topics", f"[bold yellow]{stable_count}[/bold yellow]"
            )
            summary_table.add_row("Analysis Period", f"{months_back} months ({period})")

            console.print(summary_table)

            # Display trends table
            console.print(
                f"\n[bold]📈 Topic Trends (Most Recent {period.title()} Period)[/bold]"
            )

            trends_table = Table(show_header=True, header_style="bold magenta")
            trends_table.add_column("Rank", style="dim", justify="center", width=6)
            trends_table.add_column("Topic", style="white", width=25)
            trends_table.add_column("Period", style="cyan", justify="center", width=12)
            trends_table.add_column("Videos", style="blue", justify="right", width=8)
            trends_table.add_column(
                "Channels", style="purple", justify="right", width=10
            )
            trends_table.add_column(
                "Growth Rate", style="bold white", justify="right", width=12
            )
            trends_table.add_column("Trend", style="yellow", justify="center", width=10)

            for rank, trend in enumerate(trends, 1):
                # Color-code growth rate
                growth_rate = float(trend.growth_rate)
                if growth_rate > 20:
                    growth_color = "bold green"
                    growth_icon = "🚀"
                elif growth_rate > 0:
                    growth_color = "green"
                    growth_icon = "📈"
                elif growth_rate > -20:
                    growth_color = "yellow"
                    growth_icon = "📊"
                else:
                    growth_color = "red"
                    growth_icon = "📉"

                # Trend direction icons
                trend_icon = {"growing": "⬆️", "declining": "⬇️", "stable": "➡️"}.get(
                    trend.trend_direction, "➡️"
                )

                # Format growth rate
                if growth_rate == 0:
                    growth_display = f"[{growth_color}]0.0%[/{growth_color}]"
                elif growth_rate > 100:
                    growth_display = (
                        f"[{growth_color}]{growth_icon}+100%[/{growth_color}]"
                    )
                else:
                    growth_display = f"[{growth_color}]{growth_icon}{growth_rate:+.1f}%[/{growth_color}]"

                # Topic name truncation
                topic_name = (
                    trend.category_name[:22] + "..."
                    if len(trend.category_name) > 25
                    else trend.category_name
                )

                trends_table.add_row(
                    f"#{rank}",
                    topic_name,
                    trend.period,
                    f"{trend.video_count:,}",
                    f"{trend.channel_count:,}",
                    growth_display,
                    f"{trend_icon} {trend.trend_direction.title()}",
                )

            console.print(trends_table)

            # Show analysis insights
            if trends:
                console.print(f"\n[bold]🔍 Trend Insights[/bold]")

                # Top growers
                top_growers = sorted(trends, key=lambda x: x.growth_rate, reverse=True)[
                    :3
                ]
                if top_growers and top_growers[0].growth_rate > 0:
                    console.print(
                        f"[green]🚀 Fastest Growing:[/green] {top_growers[0].category_name} (+{top_growers[0].growth_rate:.1f}%)"
                    )

                # Biggest decliners
                decliners = sorted(trends, key=lambda x: x.growth_rate)[:3]
                if decliners and decliners[0].growth_rate < 0:
                    console.print(
                        f"[red]📉 Biggest Decliner:[/red] {decliners[0].category_name} ({decliners[0].growth_rate:.1f}%)"
                    )

                # Most active
                most_active = sorted(
                    trends, key=lambda x: x.video_count + x.channel_count, reverse=True
                )[:1]
                if most_active:
                    total_activity = (
                        most_active[0].video_count + most_active[0].channel_count
                    )
                    console.print(
                        f"[bold]📊 Most Active:[/bold] {most_active[0].category_name} ({total_activity:,} total activity)"
                    )

                # Average growth rate
                avg_growth = sum(float(t.growth_rate) for t in trends) / len(trends)
                avg_color = (
                    "green" if avg_growth > 0 else "red" if avg_growth < 0 else "yellow"
                )
                console.print(
                    f"[{avg_color}]📈 Average Growth Rate:[/{avg_color}] {avg_growth:+.1f}%"
                )

            # Show metadata
            console.print(
                f"\n[dim]Analysis period: {period} | Lookback: {months_back} months | Topics: {len(trends)}[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error during trends analysis: {e}[/red]",
                    title="Analysis Error",
                    border_style="red",
                )
            )

    asyncio.run(run_trends())


@topic_app.command("insights")
def topic_insights_analysis(
    user_id: str = typer.Option(
        "default_user", "--user-id", "-u", help="User ID for personalized insights"
    ),
    limit_per_category: int = typer.Option(
        5, "--limit", "-l", help="Number of insights per category to show"
    ),
) -> None:
    """Generate personalized topic insights and recommendations."""

    async def run_insights() -> None:
        try:
            console.print(
                Panel(
                    "[bold green]🎯 Personalized Topic Insights[/bold green]\n\n"
                    "Discover your topic interests, emerging patterns, and personalized recommendations.\n"
                    "Get insights into your content consumption habits and explore new interests!",
                    title="Topic Insights",
                    border_style="green",
                    padding=(1, 2),
                )
            )

            analytics_service = TopicAnalyticsService()

            # Run insights analysis with progress indicator
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(
                    f"Analyzing personalized insights for user '{user_id}'...",
                    total=None,
                )
                insights = await analytics_service.get_topic_insights(
                    user_id=user_id, limit_per_category=limit_per_category
                )

            if insights.topics_explored == 0:
                console.print(
                    Panel(
                        f"[yellow]📊 No user data found for user '{user_id}'[/yellow]\n\n"
                        "Personalized insights require:\n"
                        "• User watch history with video interactions\n"
                        "• Video-topic associations\n"
                        "• User engagement data (likes, completion rates)\n\n"
                        "Try running [cyan]chronovista sync history[/cyan] first to import user data.",
                        title="No User Data",
                        border_style="yellow",
                    )
                )
                return

            # Display user overview
            console.print(f"\n[bold]👤 User Profile: {insights.user_id}[/bold]")

            overview_table = Table(show_header=True, header_style="bold cyan")
            overview_table.add_column("Metric", style="cyan")
            overview_table.add_column("Value", style="bold white", justify="right")

            overview_table.add_row(
                "Total Watch Time", f"{insights.total_watched_hours:.1f} hours"
            )
            overview_table.add_row("Topics Explored", f"{insights.topics_explored:,}")
            overview_table.add_row("Diversity Score", f"{insights.diversity_score:.2f}")
            overview_table.add_row(
                "Exploration Trend", f"{insights.exploration_trend.title()}"
            )

            console.print(overview_table)

            # Display dominant interests
            if insights.dominant_interests:
                console.print(f"\n[bold]🎯 Your Dominant Interests[/bold]")
                console.print(
                    "[dim]Topics you engage with most frequently and deeply[/dim]"
                )

                dominant_table = Table(show_header=True, header_style="bold green")
                dominant_table.add_column(
                    "Rank", style="dim", justify="center", width=6
                )
                dominant_table.add_column("Topic", style="green", width=25)
                dominant_table.add_column(
                    "Watch Time", style="blue", justify="right", width=12
                )
                dominant_table.add_column(
                    "Completion", style="yellow", justify="right", width=12
                )
                dominant_table.add_column(
                    "Engagement", style="purple", justify="right", width=12
                )
                dominant_table.add_column(
                    "Growth Potential", style="cyan", justify="center", width=15
                )

                for i, insight in enumerate(insights.dominant_interests, 1):
                    rank_style = "gold1" if i <= 3 else "white"
                    rank_emoji = (
                        "🥇"
                        if i == 1
                        else ("🥈" if i == 2 else ("🥉" if i == 3 else f"#{i}"))
                    )

                    completion_pct = float(insight.completion_rate)
                    completion_color = (
                        "green"
                        if completion_pct >= 70
                        else "yellow" if completion_pct >= 40 else "red"
                    )

                    engagement_pct = float(insight.user_engagement * 100)
                    engagement_color = (
                        "green"
                        if engagement_pct >= 70
                        else "yellow" if engagement_pct >= 40 else "red"
                    )

                    growth_icon = (
                        "🚀"
                        if insight.growth_potential == "high"
                        else "📈" if insight.growth_potential == "medium" else "➡️"
                    )

                    topic_name = (
                        insight.category_name[:22] + "..."
                        if len(insight.category_name) > 25
                        else insight.category_name
                    )

                    dominant_table.add_row(
                        f"[{rank_style}]{rank_emoji}[/{rank_style}]",
                        topic_name,
                        f"{insight.watch_time_hours:.1f}h",
                        f"[{completion_color}]{completion_pct:.0f}%[/{completion_color}]",
                        f"[{engagement_color}]{engagement_pct:.0f}%[/{engagement_color}]",
                        f"{growth_icon} {insight.growth_potential.title()}",
                    )

                console.print(dominant_table)

            # Display emerging interests
            if insights.emerging_interests:
                console.print(f"\n[bold]🌱 Emerging Interests[/bold]")
                console.print(
                    "[dim]Topics showing recent growth in your engagement[/dim]"
                )

                emerging_table = Table(show_header=True, header_style="bold orange1")
                emerging_table.add_column("Topic", style="orange1", width=25)
                emerging_table.add_column(
                    "Growth", style="green", justify="right", width=12
                )
                emerging_table.add_column(
                    "Potential", style="yellow", justify="right", width=12
                )
                emerging_table.add_column("Reason", style="dim", width=40)

                for insight in insights.emerging_interests:
                    topic_name = (
                        insight.category_name[:22] + "..."
                        if len(insight.category_name) > 25
                        else insight.category_name
                    )

                    potential_pct = float(insight.potential_interest_score * 100)
                    potential_color = (
                        "green"
                        if potential_pct >= 70
                        else "yellow" if potential_pct >= 40 else "red"
                    )

                    emerging_table.add_row(
                        topic_name,
                        f"🌱 {insight.growth_potential.title()}",
                        f"[{potential_color}]{potential_pct:.0f}%[/{potential_color}]",
                        (
                            insight.recommendation_reason[:37] + "..."
                            if len(insight.recommendation_reason) > 40
                            else insight.recommendation_reason
                        ),
                    )

                console.print(emerging_table)

            # Display underexplored topics
            if insights.underexplored_topics:
                console.print(f"\n[bold]🔍 Topics to Explore[/bold]")
                console.print(
                    "[dim]Popular topics you haven't fully explored yet[/dim]"
                )

                underexplored_table = Table(show_header=True, header_style="bold blue")
                underexplored_table.add_column("Topic", style="blue", width=25)
                underexplored_table.add_column(
                    "Popularity", style="purple", justify="right", width=12
                )
                underexplored_table.add_column(
                    "Content", style="cyan", justify="right", width=12
                )
                underexplored_table.add_column("Why Explore", style="dim", width=40)

                for insight in insights.underexplored_topics:
                    topic_name = (
                        insight.category_name[:22] + "..."
                        if len(insight.category_name) > 25
                        else insight.category_name
                    )

                    potential_pct = float(insight.potential_interest_score * 100)
                    potential_color = (
                        "green"
                        if potential_pct >= 70
                        else "yellow" if potential_pct >= 40 else "red"
                    )

                    underexplored_table.add_row(
                        topic_name,
                        f"[{potential_color}]{potential_pct:.0f}%[/{potential_color}]",
                        f"{insight.suggested_content_count:,} items",
                        (
                            insight.recommendation_reason[:37] + "..."
                            if len(insight.recommendation_reason) > 40
                            else insight.recommendation_reason
                        ),
                    )

                console.print(underexplored_table)

            # Display similar recommendations
            if insights.similar_recommendations:
                console.print(f"\n[bold]🎯 Similar Topic Recommendations[/bold]")
                console.print(
                    "[dim]Topics similar to your favorites that you might enjoy[/dim]"
                )

                similar_table = Table(show_header=True, header_style="bold magenta")
                similar_table.add_column("Topic", style="magenta", width=25)
                similar_table.add_column(
                    "Similarity", style="green", justify="right", width=12
                )
                similar_table.add_column(
                    "Content", style="blue", justify="right", width=12
                )
                similar_table.add_column("Why Similar", style="dim", width=40)

                for insight in insights.similar_recommendations:
                    topic_name = (
                        insight.category_name[:22] + "..."
                        if len(insight.category_name) > 25
                        else insight.category_name
                    )

                    similarity_pct = float(insight.confidence_score * 100)
                    similarity_color = (
                        "green"
                        if similarity_pct >= 70
                        else "yellow" if similarity_pct >= 40 else "red"
                    )

                    similar_table.add_row(
                        topic_name,
                        f"[{similarity_color}]{similarity_pct:.0f}%[/{similarity_color}]",
                        f"{insight.suggested_content_count:,} videos",
                        (
                            insight.recommendation_reason[:37] + "..."
                            if len(insight.recommendation_reason) > 40
                            else insight.recommendation_reason
                        ),
                    )

                console.print(similar_table)

            # Show personalized insights summary
            console.print(f"\n[bold]💡 Key Insights[/bold]")

            # Calculate some interesting stats
            total_insights = (
                len(insights.dominant_interests)
                + len(insights.emerging_interests)
                + len(insights.underexplored_topics)
                + len(insights.similar_recommendations)
            )
            diversity_rating = (
                "High"
                if insights.diversity_score > 0.7
                else "Medium" if insights.diversity_score > 0.4 else "Low"
            )

            # Exploration trend analysis
            trend_message = {
                "expanding": "🚀 You're actively exploring new topics! Keep discovering new interests.",
                "stable": "⚖️ You have consistent viewing patterns across your favorite topics.",
                "narrowing": "🎯 You're focusing more deeply on specific topics you love.",
            }.get(insights.exploration_trend, "📊 Your exploration pattern is unique.")

            console.print(
                f"🔢 Total Personalized Insights: [bold]{total_insights}[/bold]"
            )
            console.print(
                f"📊 Content Diversity: [bold]{diversity_rating}[/bold] ({insights.diversity_score:.2f})"
            )
            console.print(f"📈 {trend_message}")

            if insights.dominant_interests:
                console.print(
                    f"⭐ Your top interest: [bold cyan]{insights.dominant_interests[0].category_name}[/bold cyan]"
                )

            # Show analysis metadata
            console.print(
                f"\n[dim]Analysis completed on {insights.analysis_date[:19].replace('T', ' ')} | User: {insights.user_id}[/dim]"
            )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error during insights analysis: {e}[/red]",
                    title="Analysis Error",
                    border_style="red",
                )
            )

    asyncio.run(run_insights())


async def show_selected_topics_analysis(
    selected_topics: List[Any],
    analytics_service: TopicAnalyticsService,
    topic_repo: TopicCategoryRepository,
    console: Console,
    show_analytics: bool,
) -> None:
    """Show detailed analysis of selected topics with progress bars."""
    console.print(
        f"\n[blue]📊 Analyzing {len(selected_topics)} selected topics...[/blue]"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        analysis_task = progress.add_task(
            "Analyzing topics...", total=len(selected_topics)
        )

        topic_analyses = []

        for topic in selected_topics:
            progress.update(
                analysis_task,
                advance=1,
                description=f"Analyzing {topic.category_name}...",
            )

            if show_analytics:
                # Get relationships for this topic
                relationships = await analytics_service.get_topic_relationships(
                    topic_id=topic.topic_id, min_confidence=0.1, limit=5
                )
                topic_analyses.append({"topic": topic, "relationships": relationships})
            else:
                topic_analyses.append({"topic": topic, "relationships": None})

            # Small delay for visual effect
            import asyncio

            await asyncio.sleep(0.1)

    # Display results
    console.print(f"\n[bold green]📈 Analysis Results[/bold green]")

    for i, analysis in enumerate(topic_analyses, 1):
        topic = analysis["topic"]
        relationships = analysis["relationships"]

        # Basic topic info
        console.print(
            f"\n[bold cyan]{i}. {topic.category_name}[/bold cyan] (ID: {topic.topic_id})"
        )

        if show_analytics and relationships:
            console.print(
                f"   📺 {relationships.total_videos:,} videos • 📢 {relationships.total_channels:,} channels"
            )

            if relationships.relationships:
                console.print(
                    f"   🔗 Related topics: {', '.join([r.category_name for r in relationships.relationships[:3]])}"
                )
            else:
                console.print(f"   🔗 No strong relationships found")
        else:
            console.print(f"   📋 Topic type: {topic.topic_type}")


async def export_selected_topics(selected_topics: List[Any], console: Console) -> None:
    """Export selected topics to a file with progress bar."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"selected_topics_{timestamp}.json"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        export_task = progress.add_task("Exporting topics...", total=None)

        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_topics": len(selected_topics),
            "topics": [
                {
                    "topic_id": topic.topic_id,
                    "category_name": topic.category_name,
                    "topic_type": topic.topic_type,
                    "parent_topic_id": topic.parent_topic_id,
                }
                for topic in selected_topics
            ],
        }

        # Simulate export progress
        import asyncio

        await asyncio.sleep(0.5)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        progress.update(export_task, description="Export complete!")
        await asyncio.sleep(0.3)

    console.print(
        Panel(
            f"[bold green]✅ Export Complete![/bold green]\n\n"
            f"📄 File: {filename}\n"
            f"🏷️ Topics: {len(selected_topics)}\n"
            f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"[dim]File saved in current directory[/dim]",
            title="Export Summary",
            border_style="green",
        )
    )


@topic_app.command("engagement")
def topic_engagement_analysis(
    topic_id: Optional[str] = typer.Option(
        None, "--topic-id", "-t", help="Specific topic ID to analyze (optional)"
    ),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of topics to show"
    ),
    sort_by: str = typer.Option(
        "engagement_score",
        "--sort-by",
        "-s",
        help="Sort by: engagement_score, engagement_rate, avg_likes, avg_views",
    ),
) -> None:
    """Analyze topic engagement metrics based on likes, views, and comments."""

    async def run_engagement() -> None:
        try:
            analytics_service = TopicAnalyticsService()

            # Validate sort_by parameter
            valid_sorts = [
                "engagement_score",
                "engagement_rate",
                "avg_likes",
                "avg_views",
                "avg_comments",
            ]
            if sort_by not in valid_sorts:
                console.print(
                    Panel(
                        f"[red]❌ Invalid sort field '{sort_by}'.[/red]\n"
                        f"[yellow]💡 Valid options:[/yellow] {', '.join(valid_sorts)}\n"
                        f"[dim]Example: chronovista topics engagement --sort-by engagement_score[/dim]",
                        title="Invalid Parameter",
                        border_style="red",
                    )
                )
                return

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                if topic_id:
                    progress.add_task(
                        f"Analyzing engagement for topic {topic_id}...", total=None
                    )
                else:
                    progress.add_task(
                        "Analyzing engagement across all topics...", total=None
                    )

                # Get engagement scores
                engagement_data = await analytics_service.get_topic_engagement_scores(
                    topic_id=topic_id, limit=limit
                )

            if not engagement_data:
                console.print(
                    Panel(
                        "[yellow]No engagement data found.[/yellow]\n"
                        "This could be because:\n"
                        "• No topics have engagement metrics (likes, views, comments)\n"
                        "• The specified topic doesn't exist\n"
                        "• All videos have been deleted",
                        title="No Engagement Data",
                        border_style="yellow",
                    )
                )
                return

            # Sort data if needed (data comes pre-sorted by engagement_rate by default)
            if sort_by != "engagement_rate":
                reverse_sort = True  # Most metrics should be descending
                engagement_data.sort(
                    key=lambda x: x.get(sort_by, 0), reverse=reverse_sort
                )

            # Display results
            if topic_id:
                title = f"🎯 Engagement Analysis: {engagement_data[0]['category_name']}"
            else:
                title = f"📊 Topic Engagement Analysis (Top {len(engagement_data)})"

            console.print(
                Panel(
                    f"[bold cyan]Analysis Details[/bold cyan]\n"
                    f"📈 Topics analyzed: {len(engagement_data)}\n"
                    f"🔄 Sorted by: {sort_by}\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    title=title,
                    border_style="cyan",
                )
            )

            # Create engagement table
            table = Table(
                title=f"🚀 Topic Engagement Metrics",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Rank", style="bold cyan", width=6)
            table.add_column("Topic", style="green", width=25)
            table.add_column("Videos", style="blue", justify="right", width=8)
            table.add_column("Avg Likes", style="yellow", justify="right", width=10)
            table.add_column("Avg Views", style="cyan", justify="right", width=12)
            table.add_column("Avg Comments", style="magenta", justify="right", width=12)
            table.add_column(
                "Engagement Rate", style="bright_green", justify="right", width=15
            )
            table.add_column(
                "Score", style="bold bright_blue", justify="right", width=8
            )
            table.add_column("Tier", style="bold", width=8)

            for idx, topic in enumerate(engagement_data, 1):
                # Style tier with colors
                tier = topic["engagement_tier"]
                if tier == "High":
                    tier_style = "[bold green]High[/bold green]"
                elif tier == "Medium":
                    tier_style = "[yellow]Medium[/yellow]"
                else:
                    tier_style = "[dim]Low[/dim]"

                # Format numbers for display
                avg_likes = f"{topic['avg_likes']:,.1f}"
                avg_views = f"{topic['avg_views']:,.0f}"
                avg_comments = f"{topic['avg_comments']:,.1f}"
                engagement_rate = f"{topic['engagement_rate']:.2f}%"
                engagement_score = f"{topic['engagement_score']:.1f}"

                table.add_row(
                    str(idx),
                    (
                        topic["category_name"][:24] + "..."
                        if len(topic["category_name"]) > 24
                        else topic["category_name"]
                    ),
                    str(topic["video_count"]),
                    avg_likes,
                    avg_views,
                    avg_comments,
                    engagement_rate,
                    engagement_score,
                    tier_style,
                )

            console.print(table)

            # Show engagement insights
            if len(engagement_data) >= 3:
                high_engagement = [
                    t for t in engagement_data if t["engagement_tier"] == "High"
                ]
                low_engagement = [
                    t for t in engagement_data if t["engagement_tier"] == "Low"
                ]

                insights = []
                if high_engagement:
                    insights.append(f"🔥 {len(high_engagement)} high-engagement topics")
                if low_engagement:
                    insights.append(f"📉 {len(low_engagement)} low-engagement topics")

                avg_score = sum(t["engagement_score"] for t in engagement_data) / len(
                    engagement_data
                )
                insights.append(f"📊 Average engagement score: {avg_score:.1f}")

                if insights:
                    console.print(
                        Panel(
                            "\n".join(f"• {insight}" for insight in insights),
                            title="💡 Engagement Insights",
                            border_style="blue",
                        )
                    )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error during engagement analysis: {e}[/red]",
                    title="Analysis Error",
                    border_style="red",
                )
            )

    asyncio.run(run_engagement())


@topic_app.command("channel-engagement")
def channel_engagement_analysis(
    topic: str = typer.Argument(
        ..., help="Topic ID or name (e.g., '10' or 'Music')"
    ),
    limit: int = typer.Option(
        10, "--limit", "-l", help="Maximum number of channels to show"
    ),
) -> None:
    """Analyze channel engagement metrics for a specific topic."""

    async def run_channel_engagement() -> None:
        try:
            analytics_service = TopicAnalyticsService()
            topic_repo = TopicCategoryRepository()

            # Resolve topic by ID or name first
            async for session in db_manager.get_session(echo=False):
                resolved_topic = await resolve_topic_identifier(session, topic_repo, topic)
                if not resolved_topic:
                    console.print(
                        Panel(
                            f"[red]Topic '{topic}' not found[/red]",
                            title="Topic Not Found",
                            border_style="red",
                        )
                    )
                    return

                topic_id = resolved_topic.topic_id
                topic_name = resolved_topic.category_name

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(
                    f"Analyzing channel engagement for {topic_name}...", total=None
                )

                # Get channel engagement data
                channel_data = await analytics_service.get_channel_engagement_by_topic(
                    topic_id=topic_id, limit=limit
                )

            if not channel_data:
                console.print(
                    Panel(
                        f"[yellow]No channel engagement data found for topic '{topic_name}'.[/yellow]\n"
                        "This could be because:\n"
                        "• No channels have videos with engagement metrics for this topic\n"
                        "• All videos have been deleted",
                        title="No Channel Data",
                        border_style="yellow",
                    )
                )
                return

            # Display results
            console.print(
                Panel(
                    f"[bold cyan]Channel Engagement Analysis[/bold cyan]\n"
                    f"🎯 Topic: {topic_name} (ID: {topic_id})\n"
                    f"📊 Channels analyzed: {len(channel_data)}\n"
                    f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    title="🏢 Channel Performance",
                    border_style="cyan",
                )
            )

            # Create channel engagement table
            table = Table(
                title=f"📺 Channel Engagement for Topic: {topic_name}",
                show_header=True,
                header_style="bold magenta",
            )

            table.add_column("Rank", style="bold cyan", width=6)
            table.add_column("Channel", style="green", width=25)
            table.add_column("Videos", style="blue", justify="right", width=8)
            table.add_column("Avg Likes", style="yellow", justify="right", width=10)
            table.add_column("Avg Views", style="cyan", justify="right", width=12)
            table.add_column("Avg Comments", style="magenta", justify="right", width=12)
            table.add_column(
                "Total Views", style="bright_blue", justify="right", width=12
            )
            table.add_column(
                "Engagement Rate", style="bright_green", justify="right", width=15
            )

            for idx, channel in enumerate(channel_data, 1):
                # Format numbers for display
                avg_likes = f"{channel['avg_likes']:,.1f}"
                avg_views = f"{channel['avg_views']:,.0f}"
                avg_comments = f"{channel['avg_comments']:,.1f}"
                total_views = f"{channel['total_views']:,.0f}"
                engagement_rate = f"{channel['engagement_rate']:.2f}%"

                table.add_row(
                    str(idx),
                    (
                        channel["channel_name"][:24] + "..."
                        if len(channel["channel_name"]) > 24
                        else channel["channel_name"]
                    ),
                    str(channel["video_count"]),
                    avg_likes,
                    avg_views,
                    avg_comments,
                    total_views,
                    engagement_rate,
                )

            console.print(table)

            # Show channel insights
            if len(channel_data) >= 3:
                top_channel = channel_data[0]
                total_videos = sum(c["video_count"] for c in channel_data)
                avg_engagement = sum(c["engagement_rate"] for c in channel_data) / len(
                    channel_data
                )

                console.print(
                    Panel(
                        f"🏆 Top performer: {top_channel['channel_name']} ({top_channel['engagement_rate']:.2f}% engagement)\n"
                        f"📊 Total videos analyzed: {total_videos}\n"
                        f"📈 Average engagement rate: {avg_engagement:.2f}%",
                        title="📊 Channel Insights",
                        border_style="blue",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]❌ Error during channel engagement analysis: {e}[/red]",
                    title="Analysis Error",
                    border_style="red",
                )
            )

    asyncio.run(run_channel_engagement())
