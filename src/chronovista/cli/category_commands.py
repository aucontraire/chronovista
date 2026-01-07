"""
Category CLI commands for chronovista.

Commands for exploring YouTube video categories (creator-assigned categoryId).
These are different from Freebase topics - categories are what video creators
select when uploading (e.g., "Comedy", "Music", "Gaming").
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional, cast

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from sqlalchemy import func, select

from chronovista.config.database import db_manager
from chronovista.db.models import VideoCategory as VideoCategoryDB
from chronovista.repositories.video_category_repository import VideoCategoryRepository
from chronovista.repositories.video_repository import VideoRepository

console = Console()


async def resolve_category_identifier(
    session: Any,
    category_repo: VideoCategoryRepository,
    identifier: str,
) -> Optional[VideoCategoryDB]:
    """
    Resolve a category identifier (ID or name) to a category object.

    Accepts either:
    - A category ID (e.g., "23", "10")
    - A category name (e.g., "Comedy", "Music")

    If the name matches multiple categories, prompts for disambiguation.

    Parameters
    ----------
    session : AsyncSession
        Database session
    category_repo : VideoCategoryRepository
        Video category repository
    identifier : str
        Category ID or name to resolve

    Returns
    -------
    Optional[VideoCategoryDB]
        Resolved category or None if not found/cancelled
    """
    # First, try exact ID match
    category = await category_repo.get(session, identifier)
    if category:
        return category

    # Try exact name match (case-insensitive)
    result = await session.execute(
        select(VideoCategoryDB).where(
            func.lower(VideoCategoryDB.name) == identifier.lower()
        )
    )
    matches: List[VideoCategoryDB] = list(result.scalars().all())

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        # Disambiguation needed
        console.print(f"\n[yellow]Multiple categories match '{identifier}':[/yellow]\n")
        for i, match in enumerate(matches, 1):
            console.print(f"  {i}. [cyan]{match.name}[/cyan] - ID: {match.category_id}")

        console.print()
        choice = Prompt.ask(
            "Select category number (or 'q' to cancel)",
            choices=[str(i) for i in range(1, len(matches) + 1)] + ["q"],
            default="1",
        )

        if choice == "q":
            return None

        return matches[int(choice) - 1]

    # Try partial name match as fallback
    partial_matches = await category_repo.find_by_name(session, identifier)
    if len(partial_matches) == 1:
        return partial_matches[0]

    if len(partial_matches) > 1:
        console.print(
            f"\n[yellow]Multiple categories partially match '{identifier}':[/yellow]\n"
        )
        # Limit to first 10 for readability
        display_matches = partial_matches[:10]
        for i, match in enumerate(display_matches, 1):
            console.print(f"  {i}. [cyan]{match.name}[/cyan] - ID: {match.category_id}")

        if len(partial_matches) > 10:
            console.print(f"  ... and {len(partial_matches) - 10} more")

        console.print()
        valid_choices = [str(i) for i in range(1, len(display_matches) + 1)] + ["q"]
        choice = Prompt.ask(
            "Select category number (or 'q' to cancel)",
            choices=valid_choices,
            default="1",
        )

        if choice == "q":
            return None

        return display_matches[int(choice) - 1]

    return None


category_app = typer.Typer(
    name="categories",
    help="📂 Video category exploration (creator-assigned categories)",
    no_args_is_help=True,
)


@category_app.command("list")
def list_categories(
    assignable_only: bool = typer.Option(
        False,
        "--assignable-only",
        "-a",
        help="Only show categories that creators can assign",
    ),
) -> None:
    """List all YouTube video categories with video counts."""

    async def run_list() -> None:
        try:
            category_repo = VideoCategoryRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                # Get categories
                if assignable_only:
                    categories = await category_repo.get_assignable(session)
                else:
                    categories = await category_repo.get_all(session)

                if not categories:
                    console.print(
                        Panel(
                            "[yellow]No categories found in database[/yellow]\n"
                            "Use 'chronovista seed categories' to populate from YouTube API",
                            title="No Categories",
                            border_style="yellow",
                        )
                    )
                    return

                # Create table
                category_table = Table(
                    title=f"YouTube Video Categories ({len(categories)} total)",
                    show_header=True,
                    header_style="bold blue",
                )
                category_table.add_column("ID", style="cyan", width=6)
                category_table.add_column("Name", style="white", width=30)
                category_table.add_column("Assignable", style="green", width=12)
                category_table.add_column("Videos", style="yellow", width=12)

                for cat in categories:
                    video_count = await video_repo.count_by_category_id(
                        session, cat.category_id
                    )
                    assignable_str = "Yes" if cat.assignable else "No"
                    category_table.add_row(
                        cat.category_id,
                        cat.name,
                        assignable_str,
                        f"{video_count:,}" if video_count > 0 else "-",
                    )

                console.print(category_table)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error listing categories: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_list())


@category_app.command("show")
def show_category(
    category: str = typer.Argument(
        ..., help="Category ID or name (e.g., '23' or 'Comedy')"
    )
) -> None:
    """Show detailed information about a specific category."""

    async def run_show() -> None:
        try:
            category_repo = VideoCategoryRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                resolved_category = await resolve_category_identifier(
                    session, category_repo, category
                )

                if not resolved_category:
                    console.print(
                        Panel(
                            f"[red]Category '{category}' not found[/red]\n"
                            "Use 'chronovista categories list' to see available categories",
                            title="Category Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Get video count
                video_count = await video_repo.count_by_category_id(
                    session, resolved_category.category_id
                )

                # Show category details
                details = f"""[bold]Category ID:[/bold] {resolved_category.category_id}
[bold]Name:[/bold] {resolved_category.name}
[bold]Assignable:[/bold] {"Yes" if resolved_category.assignable else "No"}
[bold]Videos in this category:[/bold] {video_count:,}
[bold]Created:[/bold] {resolved_category.created_at.strftime('%Y-%m-%d %H:%M:%S')}"""

                console.print(
                    Panel(
                        details,
                        title=f"Category: {resolved_category.name}",
                        border_style="blue",
                    )
                )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error showing category: {str(e)}[/red]",
                    title="Error",
                    border_style="red",
                )
            )

    asyncio.run(run_show())


@category_app.command("videos")
def videos_by_category(
    category: str = typer.Argument(
        ..., help="Category ID or name (e.g., '23' or 'Comedy')"
    ),
    limit: int = typer.Option(
        20, "--limit", "-l", help="Maximum number of videos to show"
    ),
    include_deleted: bool = typer.Option(
        False, "--include-deleted", help="Include deleted videos"
    ),
) -> None:
    """Show videos in a specific category (ordered by view count)."""

    async def run_videos() -> None:
        try:
            category_repo = VideoCategoryRepository()
            video_repo = VideoRepository()

            async for session in db_manager.get_session(echo=False):
                # Resolve category by ID or name
                resolved_category = await resolve_category_identifier(
                    session, category_repo, category
                )
                if not resolved_category:
                    console.print(
                        Panel(
                            f"[red]Category '{category}' not found[/red]\n"
                            "Use 'chronovista categories list' to see available categories",
                            title="Category Not Found",
                            border_style="red",
                        )
                    )
                    return

                # Get total count
                total_count = await video_repo.count_by_category_id(
                    session,
                    resolved_category.category_id,
                    exclude_deleted=not include_deleted,
                )

                if total_count == 0:
                    console.print(
                        Panel(
                            f"[yellow]No videos found in category "
                            f"'{resolved_category.name}'[/yellow]",
                            title="No Videos",
                            border_style="yellow",
                        )
                    )
                    return

                # Get videos
                videos = await video_repo.find_by_category_id(
                    session,
                    resolved_category.category_id,
                    limit=limit,
                    exclude_deleted=not include_deleted,
                )

                # Create table
                videos_table = Table(
                    title=f"Videos in {resolved_category.name} "
                    f"(showing {len(videos)} of {total_count:,})",
                    show_header=True,
                    header_style="bold blue",
                )
                videos_table.add_column("Video ID", style="cyan", width=15)
                videos_table.add_column("Title", style="white", width=50)
                videos_table.add_column("Views", style="green", width=15)
                videos_table.add_column("Duration", style="yellow", width=10)

                for video in videos:
                    view_count = (
                        f"{video.view_count:,}" if video.view_count else "N/A"
                    )

                    # Format duration
                    if video.duration:
                        minutes, seconds = divmod(video.duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        if hours > 0:
                            duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                        else:
                            duration_str = f"{minutes}:{seconds:02d}"
                    else:
                        duration_str = "N/A"

                    # Truncate title if too long
                    title = video.title[:47] + "..." if len(video.title) > 50 else video.title

                    videos_table.add_row(
                        video.video_id,
                        title,
                        view_count,
                        duration_str,
                    )

                console.print(videos_table)

                # Show summary
                console.print(
                    f"\n[dim]Total videos in {resolved_category.name}: {total_count:,}[/dim]"
                )
                if total_count > limit:
                    console.print(
                        f"[dim]Use --limit to see more videos[/dim]"
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
