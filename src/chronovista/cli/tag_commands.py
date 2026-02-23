"""
Tag CLI commands for chronovista.

Commands for exploring YouTube video tags. Tags are keywords that video creators
add to their videos to help with discoverability and categorization.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.models.video_tag import VideoTagSearchFilters
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository

console = Console()

tag_app = typer.Typer(
    name="tags",
    help="🏷️ Video tag exploration and analytics",
    no_args_is_help=True,
)


@tag_app.command("list")
def list_tags(
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum number of tags to show"
    ),
) -> None:
    """List popular tags ordered by video count."""

    async def run_list() -> None:
        try:
            tag_repo = VideoTagRepository()

            async for session in db_manager.get_session(echo=False):
                # Get popular tags
                popular_tags = await tag_repo.get_popular_tags(session, limit=limit)

                if not popular_tags:
                    console.print(
                        Panel(
                            "[yellow]No tags found in database[/yellow]\n"
                            "Use 'chronovista enrich videos' to populate tags from YouTube API",
                            title="No Tags",
                            border_style="yellow",
                        )
                    )
                    return

                # Create table
                tag_table = Table(
                    title=f"Popular Tags (showing top {len(popular_tags)})",
                    show_header=True,
                    header_style="bold blue",
                )
                tag_table.add_column("Rank", style="dim", width=6)
                tag_table.add_column("Tag", style="cyan", width=50)
                tag_table.add_column("Videos", style="green", width=12)

                for rank, (tag, count) in enumerate(popular_tags, 1):
                    # Truncate long tags
                    display_tag = tag[:47] + "..." if len(tag) > 50 else tag
                    tag_table.add_row(str(rank), display_tag, f"{count:,}")

                console.print(tag_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error listing tags: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_list())


@tag_app.command("show")
def show_tag(
    tag: str = typer.Option(
        ...,
        "--tag",
        "-t",
        help="Tag to show details for (use --tag for tags starting with '-')",
    ),
    related_limit: int = typer.Option(
        10, "--related", "-r", help="Number of related tags to show"
    ),
) -> None:
    """Show detailed information about a specific tag."""

    async def run_show() -> None:
        try:
            tag_repo = VideoTagRepository()

            async for session in db_manager.get_session(echo=False):
                # Get video count for the tag
                video_count = await tag_repo.get_tag_video_count(session, tag)

                if video_count == 0:
                    console.print(
                        Panel(
                            f"[red]Tag '{tag}' not found[/red]\n"
                            "Use 'chronovista tags search' to find similar tags",
                            title="Tag Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Get related tags
                related_tags = await tag_repo.get_related_tags(
                    session, tag, limit=related_limit
                )

                # Show tag details
                details = f"[bold]Tag:[/bold] {tag}\n"
                details += f"[bold]Videos with this tag:[/bold] {video_count:,}"

                console.print(
                    Panel(
                        details,
                        title=f"Tag: {tag[:50]}{'...' if len(tag) > 50 else ''}",
                        border_style="blue",
                    )
                )

                # Show related tags if any
                if related_tags:
                    related_table = Table(
                        title="Related Tags (frequently appear together)",
                        show_header=True,
                        header_style="bold blue",
                    )
                    related_table.add_column("Tag", style="cyan", width=50)
                    related_table.add_column("Co-occurrences", style="green", width=15)

                    for related_tag, co_count in related_tags:
                        display_tag = (
                            related_tag[:47] + "..."
                            if len(related_tag) > 50
                            else related_tag
                        )
                        related_table.add_row(display_tag, f"{co_count:,}")

                    console.print(related_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error showing tag: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_show())


@tag_app.command("videos")
def videos_by_tag(
    tag: str = typer.Option(
        ...,
        "--tag",
        "-t",
        help="Tag to find videos for (use --tag for tags starting with '-')",
    ),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of videos to show"
    ),
) -> None:
    """Show videos with a specific tag."""

    async def run_videos() -> None:
        try:
            tag_repo = VideoTagRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                # Get video IDs with this tag
                video_ids = await tag_repo.find_videos_by_tags(
                    session, [tag], match_all=False
                )

                if not video_ids:
                    console.print(
                        Panel(
                            f"[yellow]No videos found with tag '{tag}'[/yellow]",
                            title="No Videos",
                            border_style="yellow",
                        )
                    )
                    return

                total_count = len(video_ids)
                limited_ids = video_ids[:limit]

                # Create table
                videos_table = Table(
                    title=f"Videos with tag '{tag[:30]}{'...' if len(tag) > 30 else ''}' "
                    f"(showing {len(limited_ids)} of {total_count:,})",
                    show_header=True,
                    header_style="bold blue",
                )
                videos_table.add_column("Video ID", style="cyan", width=15)
                videos_table.add_column("Title", style="white", width=50)
                videos_table.add_column("Views", style="green", width=15)

                for video_id in limited_ids:
                    video = await video_repo.get_by_video_id(session, video_id)
                    if video:
                        view_count = (
                            f"{video.view_count:,}" if video.view_count else "N/A"
                        )
                        title = (
                            video.title[:47] + "..."
                            if len(video.title) > 50
                            else video.title
                        )
                        videos_table.add_row(video.video_id, title, view_count)

                console.print(videos_table)

                if total_count > limit:
                    console.print(
                        f"\n[dim]Showing {limit} of {total_count:,} videos. "
                        f"Use --limit to see more.[/dim]"
                    )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error finding videos: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_videos())


@tag_app.command("search")
def search_tags(
    pattern: str = typer.Option(
        ...,
        "--pattern",
        "-p",
        help="Pattern to search for (use --pattern for patterns starting with '-')",
    ),
    limit: int = typer.Option(
        30, "--limit", "-l", help="Maximum number of tags to show"
    ),
) -> None:
    """Search tags by pattern (case-insensitive partial match)."""

    async def run_search() -> None:
        try:
            tag_repo = VideoTagRepository()

            async for session in db_manager.get_session(echo=False):
                # Search using filters
                filters = VideoTagSearchFilters(tag_pattern=pattern)
                results = await tag_repo.search_tags(session, filters)

                if not results:
                    console.print(
                        Panel(
                            f"[yellow]No tags found matching '{pattern}'[/yellow]",
                            title="No Results",
                            border_style="yellow",
                        )
                    )
                    return

                # Group by tag and count videos
                tag_counts: dict[str, int] = {}
                for result in results:
                    tag_counts[result.tag] = tag_counts.get(result.tag, 0) + 1

                # Sort by count descending
                sorted_tags: List[tuple[str, int]] = sorted(
                    tag_counts.items(), key=lambda x: x[1], reverse=True
                )[:limit]

                # Create table
                search_table = Table(
                    title=f"Tags matching '{pattern}' ({len(sorted_tags)} results)",
                    show_header=True,
                    header_style="bold blue",
                )
                search_table.add_column("Tag", style="cyan", width=50)
                search_table.add_column("Videos", style="green", width=12)

                for tag, count in sorted_tags:
                    display_tag = tag[:47] + "..." if len(tag) > 50 else tag
                    search_table.add_row(display_tag, f"{count:,}")

                console.print(search_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error searching tags: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_search())


@tag_app.command("stats")
def tag_stats() -> None:
    """Show comprehensive tag statistics."""

    async def run_stats() -> None:
        try:
            tag_repo = VideoTagRepository()

            async for session in db_manager.get_session(echo=False):
                stats = await tag_repo.get_video_tag_statistics(session)

                if stats.total_tags == 0:
                    console.print(
                        Panel(
                            "[yellow]No tags found in database[/yellow]\n"
                            "Use 'chronovista enrich videos' to populate tags from YouTube API",
                            title="No Tags",
                            border_style="yellow",
                        )
                    )
                    return

                # Summary panel
                summary = f"""[bold]Total Tags:[/bold] {stats.total_tags:,}
[bold]Unique Tags:[/bold] {stats.unique_tags:,}
[bold]Avg Tags per Video:[/bold] {stats.avg_tags_per_video:.1f}"""

                console.print(
                    Panel(
                        summary,
                        title="Tag Statistics",
                        border_style="blue",
                    )
                )

                # Most common tags table
                if stats.most_common_tags:
                    common_table = Table(
                        title="Top 20 Most Common Tags",
                        show_header=True,
                        header_style="bold blue",
                    )
                    common_table.add_column("Rank", style="dim", width=6)
                    common_table.add_column("Tag", style="cyan", width=50)
                    common_table.add_column("Videos", style="green", width=12)

                    for rank, (tag, count) in enumerate(stats.most_common_tags, 1):
                        display_tag = tag[:47] + "..." if len(tag) > 50 else tag
                        common_table.add_row(str(rank), display_tag, f"{count:,}")

                    console.print(common_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error getting tag statistics: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_stats())


@tag_app.command("by-video")
def tags_by_video(
    video_id: str = typer.Option(
        ...,
        "--id",
        "-i",
        help="Video ID to get tags for (use --id for IDs starting with '-')",
    ),
) -> None:
    """Show all tags for a specific video."""

    async def run_by_video() -> None:
        try:
            tag_repo = VideoTagRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                # Get video info
                video = await video_repo.get_by_video_id(session, video_id)

                if not video:
                    console.print(
                        Panel(
                            f"[red]Video '{video_id}' not found[/red]",
                            title="Video Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Get tags for video
                tags = await tag_repo.get_by_video_id(session, video_id)

                if not tags:
                    console.print(
                        Panel(
                            f"[yellow]No tags found for video '{video_id}'[/yellow]\n"
                            f"Title: {video.title}",
                            title="No Tags",
                            border_style="yellow",
                        )
                    )
                    return

                # Video info panel
                console.print(
                    Panel(
                        f"[bold]Video ID:[/bold] {video.video_id}\n"
                        f"[bold]Title:[/bold] {video.title[:80]}{'...' if len(video.title) > 80 else ''}\n"
                        f"[bold]Tag Count:[/bold] {len(tags)}",
                        title="Video Info",
                        border_style="blue",
                    )
                )

                # Tags table
                tags_table = Table(
                    title=f"Tags ({len(tags)} total)",
                    show_header=True,
                    header_style="bold blue",
                )
                tags_table.add_column("Order", style="dim", width=8)
                tags_table.add_column("Tag", style="cyan", width=60)

                for tag_obj in tags:
                    order = str(tag_obj.tag_order) if tag_obj.tag_order is not None else "-"
                    display_tag = (
                        tag_obj.tag[:57] + "..." if len(tag_obj.tag) > 60 else tag_obj.tag
                    )
                    tags_table.add_row(order, display_tag)

                console.print(tags_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error getting tags: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_by_video())


@tag_app.command("normalize")
def normalize_tags(
    batch_size: int = typer.Option(
        1000,
        "--batch-size",
        help="Number of records per transaction commit",
    ),
) -> None:
    """Normalize all video tags and populate canonical_tags/tag_aliases tables."""

    async def _run() -> None:
        from chronovista.services.tag_backfill import TagBackfillService
        from chronovista.services.tag_normalization import TagNormalizationService

        normalization_service = TagNormalizationService()
        backfill_service = TagBackfillService(normalization_service)

        async for session in db_manager.get_session(echo=False):
            await backfill_service.run_backfill(
                session, batch_size=batch_size, console=console
            )

    try:
        asyncio.run(_run())
    except SystemExit as e:
        raise typer.Exit(code=e.code if isinstance(e.code, int) else 1)


@tag_app.command("analyze")
def analyze_tags(
    output_format: str = typer.Option(
        "table",
        "--format",
        help="Output format",
        case_sensitive=False,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Accepted but no-op (analyze is always read-only)",
    ),
) -> None:
    """Analyze tag normalization without modifying the database."""

    async def _run() -> None:
        from chronovista.services.tag_backfill import TagBackfillService
        from chronovista.services.tag_normalization import TagNormalizationService

        normalization_service = TagNormalizationService()
        backfill_service = TagBackfillService(normalization_service)

        async for session in db_manager.get_session(echo=False):
            await backfill_service.run_analysis(
                session, output_format=output_format, console=console
            )

    try:
        asyncio.run(_run())
    except SystemExit as e:
        raise typer.Exit(code=e.code if isinstance(e.code, int) else 1)


@tag_app.command("recount")
def recount_tags(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview count changes without writing to the database",
    ),
) -> None:
    """Recalculate alias_count and video_count on all canonical tags."""

    async def _run() -> None:
        from chronovista.services.tag_backfill import TagBackfillService
        from chronovista.services.tag_normalization import TagNormalizationService

        normalization_service = TagNormalizationService()
        backfill_service = TagBackfillService(normalization_service)

        async for session in db_manager.get_session(echo=False):
            await backfill_service.run_recount(
                session, dry_run=dry_run, console=console
            )

    try:
        asyncio.run(_run())
    except SystemExit as e:
        raise typer.Exit(code=e.code if isinstance(e.code, int) else 1)
