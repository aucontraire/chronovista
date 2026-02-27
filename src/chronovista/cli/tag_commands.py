"""
Tag CLI commands for chronovista.

Commands for exploring YouTube video tags. Tags are keywords that video creators
add to their videos to help with discoverability and categorization.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from chronovista.services.tag_management import TagManagementService

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.models.video_tag import VideoTagSearchFilters
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Tag Management Commands (Feature 031)
# ---------------------------------------------------------------------------


def _reason_callback(value: Optional[str]) -> Optional[str]:
    """Validate --reason text length (max 1000 characters)."""
    if value is not None and len(value) > 1000:
        raise typer.BadParameter(
            f"Reason text is too long ({len(value)} chars). "
            "Maximum is 1,000 characters."
        )
    return value


def _create_tag_management_service() -> "TagManagementService":
    """Create a TagManagementService with all required repositories."""
    from chronovista.repositories.canonical_tag_repository import (
        CanonicalTagRepository,
    )
    from chronovista.repositories.entity_alias_repository import (
        EntityAliasRepository,
    )
    from chronovista.repositories.named_entity_repository import (
        NamedEntityRepository,
    )
    from chronovista.repositories.tag_alias_repository import TagAliasRepository
    from chronovista.repositories.tag_operation_log_repository import (
        TagOperationLogRepository,
    )
    from chronovista.services.tag_management import TagManagementService

    return TagManagementService(
        canonical_tag_repo=CanonicalTagRepository(),
        tag_alias_repo=TagAliasRepository(),
        named_entity_repo=NamedEntityRepository(),
        entity_alias_repo=EntityAliasRepository(),
        operation_log_repo=TagOperationLogRepository(),
    )


@tag_app.command("merge")
def merge_tags(
    sources: List[str] = typer.Argument(
        ..., help="Normalized form(s) of source tag(s) to merge"
    ),
    into: str = typer.Option(
        ..., "--into", help="Normalized form of the target tag to merge into"
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        help="Reason for the merge (max 1000 chars)",
        callback=_reason_callback,
    ),
) -> None:
    """Merge one or more source tags into a target tag."""

    async def _run() -> None:
        from chronovista.services.tag_management import MergeResult

        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            try:
                result: MergeResult = await service.merge(
                    session,
                    source_normalized_forms=sources,
                    target_normalized_form=into,
                    reason=reason,
                )
                await session.commit()

                details = (
                    f"[bold]Source(s):[/bold] {', '.join(result.source_tags)}\n"
                    f"[bold]Target:[/bold] {result.target_tag}\n"
                    f"[bold]Aliases moved:[/bold] {result.aliases_moved}\n"
                    f"[bold]Target alias count:[/bold] {result.new_alias_count}\n"
                    f"[bold]Target video count:[/bold] {result.new_video_count}\n"
                    f"[bold]Operation ID:[/bold] {result.operation_id}"
                )
                if result.entity_hint:
                    details += f"\n\n[yellow]{result.entity_hint}[/yellow]"

                console.print(
                    Panel(
                        details,
                        title="[green]Merge Successful[/green]",
                        border_style="green",
                    )
                )
            except ValueError as e:
                logger.warning("Merge validation failed: %s", e)
                console.print(
                    Panel(
                        f"[red]{e}[/red]",
                        title="Merge Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("split")
def split_tag(
    normalized_form: str = typer.Argument(
        help="Normalized form of the canonical tag to split."
    ),
    aliases: str = typer.Option(
        ...,
        "--aliases",
        help="Comma-separated list of raw alias forms to split out.",
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        callback=_reason_callback,
        help="Reason for the split (max 1000 chars).",
    ),
) -> None:
    """Split specific aliases from a canonical tag into a new tag."""

    async def _run() -> None:
        from chronovista.services.tag_management import SplitResult

        service = _create_tag_management_service()
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()]

        async for session in db_manager.get_session(echo=False):
            try:
                result: SplitResult = await service.split(
                    session,
                    normalized_form=normalized_form,
                    alias_raw_forms=alias_list,
                    reason=reason,
                )
                await session.commit()

                details = (
                    f"[bold]Original tag:[/bold] {result.original_tag}\n"
                    f"[bold]New tag:[/bold] {result.new_tag}\n"
                    f"[bold]New canonical form:[/bold] {result.new_canonical_form}\n"
                    f"[bold]Aliases moved:[/bold] {result.aliases_moved}\n"
                    f"[bold]Original alias count:[/bold] {result.original_alias_count}\n"
                    f"[bold]Original video count:[/bold] {result.original_video_count}\n"
                    f"[bold]New alias count:[/bold] {result.new_alias_count}\n"
                    f"[bold]New video count:[/bold] {result.new_video_count}\n"
                    f"[bold]Operation ID:[/bold] {result.operation_id}"
                )

                console.print(
                    Panel(
                        details,
                        title="[green]Split Successful[/green]",
                        border_style="green",
                    )
                )
            except ValueError as e:
                logger.warning("Split validation failed: %s", e)
                console.print(
                    Panel(
                        f"[red]{e}[/red]",
                        title="Split Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("rename")
def rename_tag(
    normalized_form: str = typer.Argument(
        help="Normalized form of the canonical tag to rename."
    ),
    to: str = typer.Option(
        ..., "--to", help="New display form for the canonical tag."
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        callback=_reason_callback,
        help="Reason for the rename (max 1000 chars).",
    ),
) -> None:
    """Rename a canonical tag's display form."""

    async def _run() -> None:
        from chronovista.services.tag_management import RenameResult

        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            try:
                result: RenameResult = await service.rename(
                    session,
                    normalized_form=normalized_form,
                    new_display_form=to,
                    reason=reason,
                )
                await session.commit()

                details = (
                    f"[bold]Old display form:[/bold] {result.old_form}\n"
                    f"[bold]New display form:[/bold] {result.new_form}\n"
                    f"[bold]Normalized form:[/bold] {result.normalized_form}\n"
                    f"[bold]Operation ID:[/bold] {result.operation_id}"
                )

                console.print(
                    Panel(
                        details,
                        title="[green]Rename Successful[/green]",
                        border_style="green",
                    )
                )
            except ValueError as e:
                logger.warning("Rename validation failed: %s", e)
                console.print(
                    Panel(
                        f"[red]{e}[/red]",
                        title="Rename Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("deprecate")
def deprecate_tag(
    normalized_form: Optional[str] = typer.Argument(
        None, help="Normalized form of the canonical tag to deprecate."
    ),
    list_deprecated: bool = typer.Option(
        False,
        "--list",
        is_flag=True,
        help="List all deprecated canonical tags.",
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        callback=_reason_callback,
        help="Reason for the deprecation (max 1000 chars).",
    ),
) -> None:
    """Deprecate a canonical tag (soft delete) or list deprecated tags."""

    # Mutual exclusivity check
    if list_deprecated and normalized_form is not None:
        console.print(
            Panel(
                "[red]Cannot use --list together with a tag argument.[/red]",
                title="Invalid Usage",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    if not list_deprecated and normalized_form is None:
        console.print(
            Panel(
                "[red]Provide a tag to deprecate or use --list to see "
                "deprecated tags.[/red]",
                title="Invalid Usage",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    async def _run() -> None:
        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            if list_deprecated:
                deprecated_tags = await service.list_deprecated(session)

                if not deprecated_tags:
                    console.print(
                        Panel(
                            "[yellow]No deprecated tags found.[/yellow]",
                            title="Deprecated Tags",
                            border_style="yellow",
                        )
                    )
                    return

                dep_table = Table(
                    title=f"Deprecated Tags ({len(deprecated_tags)} total)",
                    show_header=True,
                    header_style="bold blue",
                )
                dep_table.add_column("Normalized Form", style="cyan", width=40)
                dep_table.add_column("Canonical Form", style="white", width=40)
                dep_table.add_column("Aliases", style="green", width=10)
                dep_table.add_column("Videos", style="green", width=10)

                for tag in deprecated_tags:
                    dep_table.add_row(
                        tag.normalized_form,
                        tag.canonical_form,
                        str(tag.alias_count),
                        str(tag.video_count),
                    )

                console.print(dep_table)
            else:
                assert normalized_form is not None  # type narrowing
                try:
                    from chronovista.services.tag_management import DeprecateResult

                    result: DeprecateResult = await service.deprecate(
                        session,
                        normalized_form=normalized_form,
                        reason=reason,
                    )
                    await session.commit()

                    details = (
                        f"[bold]Tag:[/bold] {result.normalized_form}\n"
                        f"[bold]Canonical form:[/bold] {result.canonical_form}\n"
                        f"[bold]Aliases preserved:[/bold] {result.alias_count}\n"
                        f"[bold]Operation ID:[/bold] {result.operation_id}"
                    )

                    console.print(
                        Panel(
                            details,
                            title="[green]Deprecate Successful[/green]",
                            border_style="green",
                        )
                    )
                except ValueError as e:
                    logger.warning("Deprecate validation failed: %s", e)
                    console.print(
                        Panel(
                            f"[red]{e}[/red]",
                            title="Deprecate Failed",
                            border_style="red",
                        )
                    )
                    raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("undo")
def undo_operation(
    operation_id: Optional[str] = typer.Argument(
        None, help="UUID of the operation to undo."
    ),
    list_ops: bool = typer.Option(
        False, "--list", is_flag=True, help="List recent operations."
    ),
) -> None:
    """Undo a previous tag operation, or list recent operations."""

    async def _run() -> None:
        import uuid

        from chronovista.services.tag_management import (
            UndoNotImplementedError,
            UndoResult,
        )

        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            if list_ops:
                operations = await service.list_recent_operations(
                    session, limit=20
                )
                if not operations:
                    console.print(
                        Panel(
                            "[yellow]No operations found in the audit log[/yellow]",
                            title="No Operations",
                            border_style="yellow",
                        )
                    )
                    return

                ops_table = Table(
                    title=f"Recent Tag Operations ({len(operations)})",
                    show_header=True,
                    header_style="bold blue",
                )
                ops_table.add_column("ID", style="cyan", width=12)
                ops_table.add_column("Type", style="white", width=10)
                ops_table.add_column("Timestamp", style="white", width=20)
                ops_table.add_column("Rolled Back", width=12)
                ops_table.add_column("Reason", style="dim", width=50)

                for op in operations:
                    op_id_short = str(op.id)[:8] + "..."
                    timestamp = (
                        op.performed_at.strftime("%Y-%m-%d %H:%M:%S")
                        if op.performed_at
                        else "N/A"
                    )
                    rolled_back_str = (
                        "[green]yes[/green]"
                        if op.rolled_back
                        else "[red]no[/red]"
                    )
                    reason_str = (
                        (op.reason[:50] if len(op.reason) > 50 else op.reason)
                        if op.reason
                        else ""
                    )
                    ops_table.add_row(
                        op_id_short,
                        op.operation_type,
                        timestamp,
                        rolled_back_str,
                        reason_str,
                    )

                console.print(ops_table)
                return

            if operation_id is None:
                console.print(
                    Panel(
                        "[red]Provide an operation ID or use --list to see "
                        "recent operations[/red]",
                        title="Missing Argument",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=2)

            try:
                op_uuid = uuid.UUID(operation_id)
            except ValueError:
                console.print(
                    Panel(
                        f"[red]Invalid UUID: '{operation_id}'[/red]",
                        title="Invalid Operation ID",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

            try:
                result: UndoResult = await service.undo(session, op_uuid)
                await session.commit()

                details = (
                    f"[bold]Operation type:[/bold] {result.operation_type}\n"
                    f"[bold]Details:[/bold] {result.details}\n"
                    f"[bold]Operation ID:[/bold] {result.operation_id}"
                )

                console.print(
                    Panel(
                        details,
                        title="[green]Undo Successful[/green]",
                        border_style="green",
                    )
                )
            except ValueError as e:
                logger.warning("Undo validation failed: %s", e)
                console.print(
                    Panel(
                        f"[red]{e}[/red]",
                        title="Undo Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)
            except UndoNotImplementedError as e:
                logger.warning("Undo not implemented: %s", e)
                console.print(
                    Panel(
                        f"[red]{e}[/red]",
                        title="Undo Not Available",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("classify")
def classify_tag(
    normalized_form: Optional[str] = typer.Argument(
        None, help="Normalized form of the canonical tag to classify."
    ),
    entity_type: Optional[str] = typer.Option(
        None,
        "--type",
        help=(
            "Entity type to assign. Valid values: person, organization, "
            "place, event, work, technical_term, topic, descriptor."
        ),
    ),
    top: Optional[int] = typer.Option(
        None,
        "--top",
        help="Show top N unclassified tags by video count.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        is_flag=True,
        help="Override existing classification.",
    ),
    reason: Optional[str] = typer.Option(
        None,
        "--reason",
        callback=_reason_callback,
        help="Reason for the classification (max 1000 chars).",
    ),
) -> None:
    """Classify a canonical tag with an entity type, or list top unclassified tags."""

    # Mutual exclusivity check
    if top is not None and normalized_form is not None:
        console.print(
            Panel(
                "[red]Cannot use --top together with a tag argument. "
                "Use either --top N or provide a normalized form with --type.[/red]",
                title="Invalid Usage",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    if top is None and normalized_form is None:
        console.print(
            Panel(
                "[red]Provide a tag to classify with --type, or use --top N "
                "to see top unclassified tags.[/red]",
                title="Invalid Usage",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    if normalized_form is not None and entity_type is None:
        console.print(
            Panel(
                "[red]--type is required when classifying a tag. "
                "Valid values: person, organization, place, event, work, "
                "technical_term, topic, descriptor.[/red]",
                title="Missing --type",
                border_style="red",
            )
        )
        raise typer.Exit(code=2)

    async def _run() -> None:
        from chronovista.models.enums import EntityType
        from chronovista.services.tag_management import ClassifyResult

        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            if top is not None:
                # Show top unclassified tags
                tags = await service.classify_top_unclassified(
                    session, limit=top
                )

                if not tags:
                    console.print(
                        Panel(
                            "[yellow]No unclassified tags found.[/yellow]",
                            title="Unclassified Tags",
                            border_style="yellow",
                        )
                    )
                    return

                classify_table = Table(
                    title=f"Top {len(tags)} Unclassified Tags",
                    show_header=True,
                    header_style="bold blue",
                )
                classify_table.add_column(
                    "Normalized Form", style="cyan", width=40
                )
                classify_table.add_column(
                    "Canonical Form", style="white", width=40
                )
                classify_table.add_column(
                    "Videos", style="green", width=10
                )
                classify_table.add_column(
                    "Aliases", style="green", width=10
                )

                for tag in tags:
                    classify_table.add_row(
                        tag.normalized_form,
                        tag.canonical_form,
                        str(tag.video_count),
                        str(tag.alias_count),
                    )

                console.print(classify_table)
            else:
                assert normalized_form is not None  # type narrowing
                assert entity_type is not None  # type narrowing

                # Parse entity type string to enum
                try:
                    parsed_type = EntityType(entity_type)
                except ValueError:
                    valid_types = ", ".join(t.value for t in EntityType)
                    console.print(
                        Panel(
                            f"[red]Invalid entity type '{entity_type}'. "
                            f"Valid values: {valid_types}[/red]",
                            title="Invalid --type",
                            border_style="red",
                        )
                    )
                    raise typer.Exit(code=1)

                try:
                    result: ClassifyResult = await service.classify(
                        session,
                        normalized_form=normalized_form,
                        entity_type=parsed_type,
                        force=force,
                        reason=reason,
                    )
                    await session.commit()

                    details = (
                        f"[bold]Tag:[/bold] {result.normalized_form}\n"
                        f"[bold]Canonical form:[/bold] {result.canonical_form}\n"
                        f"[bold]Entity type:[/bold] {result.entity_type}\n"
                        f"[bold]Entity created:[/bold] {result.entity_created}\n"
                        f"[bold]Entity aliases:[/bold] {result.entity_alias_count}\n"
                        f"[bold]Operation ID:[/bold] {result.operation_id}"
                    )

                    console.print(
                        Panel(
                            details,
                            title="[green]Classify Successful[/green]",
                            border_style="green",
                        )
                    )
                except ValueError as e:
                    logger.warning("Classify validation failed: %s", e)
                    console.print(
                        Panel(
                            f"[red]{e}[/red]",
                            title="Classify Failed",
                            border_style="red",
                        )
                    )
                    raise typer.Exit(code=1)

    asyncio.run(_run())


@tag_app.command("collisions")
def review_collisions(
    format: str = typer.Option(
        "table",
        "--format",
        help="Output format: table (interactive) or json.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Maximum number of collision groups to review.",
    ),
    include_reviewed: bool = typer.Option(
        False,
        "--include-reviewed",
        help="Include previously reviewed collisions.",
    ),
) -> None:
    """Review diacritic collision candidates interactively."""
    import json as json_module

    from rich.prompt import Prompt
    from rich.table import Table

    async def _run() -> None:
        from chronovista.services.tag_management import CollisionGroup

        service = _create_tag_management_service()

        async for session in db_manager.get_session(echo=False):
            collisions: list[CollisionGroup] = await service.get_collisions(
                session,
                limit=limit,
                include_reviewed=include_reviewed,
            )

            if not collisions:
                console.print("[green]No collision candidates found.[/green]")
                return

            if format == "json":
                output = [
                    {
                        "canonical_form": c.canonical_form,
                        "normalized_form": c.normalized_form,
                        "canonical_tag_id": str(c.canonical_tag_id),
                        "aliases": c.aliases,
                        "total_occurrence_count": c.total_occurrence_count,
                    }
                    for c in collisions
                ]
                console.print(json_module.dumps(output, indent=2, default=str))
                return

            # Interactive review mode
            console.print(
                f"\n[bold]Found {len(collisions)} collision candidate(s)[/bold]\n"
            )

            for i, collision in enumerate(collisions, 1):
                console.print(
                    Panel(
                        f"[bold]Canonical form:[/bold] {collision.canonical_form}\n"
                        f"[bold]Normalized form:[/bold] {collision.normalized_form}\n"
                        f"[bold]Total occurrences:[/bold] {collision.total_occurrence_count}",
                        title=f"[yellow]Collision {i}/{len(collisions)}[/yellow]",
                        border_style="yellow",
                    )
                )

                # Show aliases table
                alias_table = Table(title="Aliases")
                alias_table.add_column("Raw Form", style="cyan")
                alias_table.add_column("Occurrences", justify="right")
                for alias in collision.aliases:
                    alias_table.add_row(
                        alias["raw_form"],
                        str(alias["occurrence_count"]),
                    )
                console.print(alias_table)

                # Prompt for action
                action = Prompt.ask(
                    "\n[bold]Action[/bold]",
                    choices=["s", "k", "n"],
                    default="n",
                )

                if action == "s":
                    # Split: ask which aliases to pull out
                    alias_forms = [a["raw_form"] for a in collision.aliases]
                    console.print(
                        f"[bold]Available aliases:[/bold] {', '.join(alias_forms)}"
                    )
                    split_input = Prompt.ask(
                        "Enter comma-separated aliases to split out"
                    )
                    split_aliases = [
                        a.strip() for a in split_input.split(",") if a.strip()
                    ]
                    if split_aliases:
                        try:
                            split_result = await service.split(
                                session,
                                normalized_form=collision.normalized_form,
                                alias_raw_forms=split_aliases,
                                reason="Split from collision review",
                            )
                            await session.commit()
                            console.print(
                                f"[green]Split successful: "
                                f"new tag '{split_result.new_tag}' with "
                                f"{split_result.aliases_moved} aliases[/green]"
                            )
                        except ValueError as e:
                            console.print(f"[red]Split failed: {e}[/red]")
                elif action == "k":
                    # Keep: mark as reviewed
                    await service.log_collision_reviewed(
                        session, collision.canonical_tag_id
                    )
                    await session.commit()
                    console.print("[green]Marked as reviewed.[/green]")
                else:
                    # Next: skip
                    console.print("[dim]Skipped.[/dim]")

                console.print()  # blank line between groups

    asyncio.run(_run())
