"""
Seed CLI commands for chronovista.

This module provides commands to seed reference data into the database:
- `topics`: Seed YouTube topic categories (~55 official topics)
- `categories`: Seed video categories from YouTube API (region-specific)

Both commands support idempotent seeding with optional force mode.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.config.database import db_manager
from chronovista.container import container
from chronovista.services.enrichment.seeders import TopicSeeder

if TYPE_CHECKING:
    from chronovista.services.enrichment.seeders import CategorySeeder

console = Console()

# Create the seed Typer app
seed_app = typer.Typer(
    name="seed",
    help="Seed reference data into the database",
    no_args_is_help=True,
)


@seed_app.command()
def topics(
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing topics (default: skip existing)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be seeded without making changes",
    ),
) -> None:
    """
    Seed YouTube topic categories.

    Seeds the official YouTube topic hierarchy (~55 topics) into the database.
    Topics include 7 parent categories (Music, Gaming, Sports, Entertainment,
    Lifestyle, Knowledge, Society) and their child topics.

    Examples:
        chronovista seed topics
        chronovista seed topics --force
        chronovista seed topics --dry-run
    """

    async def seed_topics_data() -> None:
        """Async implementation of topic seeding."""
        try:
            # Create seeder using container
            seeder = container.create_topic_seeder()

            # Handle dry-run mode
            if dry_run:
                await _show_topics_dry_run(seeder)
                return

            # Show seeding progress
            console.print(
                Panel(
                    "[blue]Seeding YouTube topic categories...[/blue]",
                    title="Topic Seeding",
                    border_style="blue",
                )
            )

            # Perform seeding
            async for session in db_manager.get_session(echo=False):
                result = await seeder.seed(session, force=force)

                # Display results
                if result.errors:
                    console.print(
                        f"[yellow]Warning: {len(result.errors)} errors occurred[/yellow]"
                    )
                    for error in result.errors[:5]:  # Show first 5 errors
                        console.print(f"  [red]✗[/red] {error}")
                    if len(result.errors) > 5:
                        console.print(
                            f"  [dim]... and {len(result.errors) - 5} more[/dim]"
                        )

                # Calculate child count for summary message
                child_count = TopicSeeder.get_child_count()

                # Create results table
                results_table = Table(title="Topic Seeding Results")
                results_table.add_column("Metric", style="cyan")
                results_table.add_column("Count", style="green")

                results_table.add_row("Topics Created", str(result.created))
                results_table.add_row("Topics Skipped", str(result.skipped))
                if force:
                    results_table.add_row("Topics Deleted", str(result.deleted))
                results_table.add_row("Failed", str(result.failed))
                results_table.add_row("Duration", f"{result.duration_seconds:.2f}s")

                console.print(results_table)

                # Summary message
                total_seeded = result.created + result.skipped
                if result.failed == 0:
                    console.print(
                        Panel(
                            f"[green]✓ Created {result.created} topic categories[/green]\n"
                            f"[green]✓ Established {child_count} parent-child relationships[/green]\n"
                            f"Done. {total_seeded} topics seeded.",
                            title="Topic Seeding Complete",
                            border_style="green",
                        )
                    )
                    sys.exit(0)
                else:
                    console.print(
                        Panel(
                            f"[yellow]⚠ Topic seeding completed with errors[/yellow]\n"
                            f"Created: {result.created}, Skipped: {result.skipped}, Failed: {result.failed}\n"
                            f"Check errors above for details.",
                            title="Topic Seeding Incomplete",
                            border_style="yellow",
                        )
                    )
                    sys.exit(1)

        except Exception as e:
            console.print(
                Panel(
                    f"[red]✗ Database error:[/red]\n{str(e)}",
                    title="Topic Seeding Failed",
                    border_style="red",
                )
            )
            sys.exit(1)

    # Run the async function
    asyncio.run(seed_topics_data())


async def _show_topics_dry_run(seeder: TopicSeeder) -> None:
    """Show what would be seeded without making changes."""
    expected_count = TopicSeeder.get_expected_topic_count()
    parent_count = TopicSeeder.get_parent_count()
    child_count = TopicSeeder.get_child_count()

    # Get parent topics with child counts
    parent_info: list[tuple[str, str, int]] = []
    for parent_id in TopicSeeder.PARENT_TOPIC_IDS:
        topic_info = TopicSeeder.get_topic_by_id(parent_id)
        if topic_info:
            category_name, _, _ = topic_info
            children = TopicSeeder.get_topics_by_parent(parent_id)
            parent_info.append((parent_id, category_name, len(children)))

    # Sort by category name for consistent display
    parent_info.sort(key=lambda x: x[1])

    # Display dry-run information
    console.print(
        Panel(
            "[blue][DRY RUN] Would seed YouTube topic categories[/blue]",
            title="Topic Seeding Preview",
            border_style="blue",
        )
    )

    console.print(f"\n[cyan]Would seed {expected_count} topic categories:[/cyan]\n")

    for parent_id, category_name, child_count in parent_info:
        console.print(f"  - {category_name} ({child_count} children)")

    console.print(
        f"\n[dim]Total: {parent_count} parent topics + {child_count} child topics = {expected_count} total[/dim]"
    )
    console.print("[yellow]No changes made.[/yellow]")


@seed_app.command()
def categories(
    regions: str = typer.Option(
        "US,GB,JP,DE,BR,IN,MX",
        "--regions",
        help="Comma-separated region codes (e.g., US,GB,JP)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing categories (default: skip existing)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be seeded without making changes",
    ),
) -> None:
    """
    Seed video categories from YouTube API.

    Fetches video categories from multiple regions and seeds them into the database.
    Categories are region-specific but category IDs are globally unique.

    Examples:
        chronovista seed categories
        chronovista seed categories --regions US,GB
        chronovista seed categories --force
        chronovista seed categories --dry-run
    """

    async def seed_categories_data() -> None:
        """Async implementation of category seeding."""
        try:
            # Parse regions
            region_list = [r.strip().upper() for r in regions.split(",")]

            # Create seeder using container
            seeder = container.create_category_seeder()

            # Handle dry-run mode
            if dry_run:
                await _show_categories_dry_run(seeder, region_list)
                return

            # Show seeding progress
            console.print(
                Panel(
                    f"[blue]Seeding video categories from {len(region_list)} regions...[/blue]\n"
                    f"Regions: {', '.join(region_list)}",
                    title="Category Seeding",
                    border_style="blue",
                )
            )

            # Perform seeding
            async for session in db_manager.get_session(echo=False):
                result = await seeder.seed(session, regions=region_list, force=force)

                # Display per-region progress (simulated - actual fetching happens inside seeder)
                for region in region_list:
                    console.print(f"  [dim]Fetching {region}...[/dim]")

                # Display errors if any
                if result.errors:
                    console.print(
                        f"\n[yellow]Warning: {len(result.errors)} errors occurred[/yellow]"
                    )
                    for error in result.errors[:3]:  # Show first 3 errors
                        console.print(f"  [red]✗[/red] {error}")
                    if len(result.errors) > 3:
                        console.print(
                            f"  [dim]... and {len(result.errors) - 3} more[/dim]"
                        )

                # Create results table
                results_table = Table(title="Category Seeding Results")
                results_table.add_column("Metric", style="cyan")
                results_table.add_column("Count", style="green")

                results_table.add_row("Categories Created", str(result.created))
                results_table.add_row("Categories Skipped", str(result.skipped))
                if force:
                    results_table.add_row("Categories Deleted", str(result.deleted))
                results_table.add_row("Failed", str(result.failed))
                results_table.add_row("Quota Used", f"{result.quota_used} units")
                results_table.add_row("Duration", f"{result.duration_seconds:.2f}s")

                console.print(results_table)

                # Summary message
                if result.failed == 0:
                    console.print(
                        Panel(
                            f"[green]✓ Created {result.created} unique categories[/green]\n"
                            f"Done. Quota used: {result.quota_used} units.",
                            title="Category Seeding Complete",
                            border_style="green",
                        )
                    )
                    sys.exit(0)
                else:
                    console.print(
                        Panel(
                            f"[yellow]⚠ Category seeding completed with errors[/yellow]\n"
                            f"Created: {result.created}, Skipped: {result.skipped}, Failed: {result.failed}\n"
                            f"Quota used: {result.quota_used} units\n"
                            f"Check errors above for details.",
                            title="Category Seeding Incomplete",
                            border_style="yellow",
                        )
                    )
                    sys.exit(2)  # Exit code 2 for API errors

        except Exception as e:
            console.print(
                Panel(
                    f"[red]✗ API error:[/red]\n{str(e)}",
                    title="Category Seeding Failed",
                    border_style="red",
                )
            )
            sys.exit(2)

    # Run the async function
    asyncio.run(seed_categories_data())


async def _show_categories_dry_run(
    seeder: CategorySeeder, region_list: list[str]
) -> None:
    """Show what would be seeded without making changes."""
    from chronovista.services.enrichment.seeders import CategorySeeder as CS

    expected_quota = CS.get_expected_quota_cost(region_list)

    # Display dry-run information
    console.print(
        Panel(
            "[blue][DRY RUN] Would seed video categories from YouTube API[/blue]",
            title="Category Seeding Preview",
            border_style="blue",
        )
    )

    console.print(
        f"\n[cyan]Would fetch categories from {len(region_list)} regions:[/cyan]\n"
    )

    for region in region_list:
        console.print(f"  - {region}")

    console.print(f"\n[cyan]Estimated API quota cost: {expected_quota} units[/cyan]")
    console.print(
        "[dim](1 unit per region, actual category count varies by region)[/dim]"
    )
    console.print("\n[yellow]No changes made.[/yellow]")
