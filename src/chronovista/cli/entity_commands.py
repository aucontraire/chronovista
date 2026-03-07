"""
Entity CLI commands for chronovista.

Commands for creating and browsing named entities. Entities represent
real-world people, organizations, places, events, and other typed objects
discovered from or associated with video tags.

Feature 037 — Entity Classify Improvements (#69)
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import func, select, update

from chronovista.config.database import db_manager
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
)
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.tag_normalization import TagNormalizationService

logger = logging.getLogger(__name__)

console = Console()

entity_app = typer.Typer(
    name="entities",
    help="Named entity management",
    no_args_is_help=True,
)

# Entity types that are valid for standalone entity creation.
# "topic" and "descriptor" are tag-only types, not entity types.
_ENTITY_PRODUCING_TYPES = {
    "person",
    "organization",
    "place",
    "event",
    "work",
    "technical_term",
}


@entity_app.command("create")
def create_entity(
    name: str = typer.Argument(
        ..., help="Canonical name for the entity (e.g., 'Noam Chomsky')."
    ),
    type_str: str = typer.Option(
        ...,
        "--type",
        help=(
            "Entity type. Valid values: person, organization, place, "
            "event, work, technical_term."
        ),
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        help="Human-readable description of the entity.",
    ),
    alias: Optional[List[str]] = typer.Option(
        None,
        "--alias",
        help="Additional alias name (repeatable).",
    ),
) -> None:
    """Create a standalone named entity (not linked to an existing canonical tag)."""

    async def _run() -> None:
        # Validate entity type
        if type_str not in _ENTITY_PRODUCING_TYPES:
            console.print(
                Panel(
                    f"[red]Entity type '{type_str}' is not valid for entities.[/red]\n"
                    "Only entity-producing types are allowed: "
                    "person, organization, place, event, work, technical_term",
                    title="Invalid Type",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        try:
            entity_type = EntityType(type_str)
        except ValueError:
            valid_types = ", ".join(t.value for t in EntityType)
            console.print(
                Panel(
                    f"[red]Invalid entity type '{type_str}'. "
                    f"Valid values: {valid_types}[/red]",
                    title="Invalid --type",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        # Normalize the name
        normalizer = TagNormalizationService()
        normalized_name = normalizer.normalize(name)

        if normalized_name is None:
            console.print(
                Panel(
                    "[red]Name normalizes to empty string. "
                    "Please provide a valid entity name.[/red]",
                    title="Invalid Name",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        # Auto-title-case canonical name for entity-producing types
        canonical_name = name.title() if not name.istitle() else name

        entity_repo = NamedEntityRepository()
        alias_repo = EntityAliasRepository()

        async for session in db_manager.get_session(echo=False):
            # Check for duplicate: same normalized name + entity type
            existing = await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_name,
                    NamedEntityDB.entity_type == entity_type.value,
                )
            )
            if existing.scalar_one_or_none() is not None:
                console.print(
                    Panel(
                        f"[red]A named entity with normalized name "
                        f"'{normalized_name}' and type '{entity_type.value}' "
                        f"already exists.[/red]",
                        title="Duplicate Entity",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

            # Create the named entity
            entity_create = NamedEntityCreate(
                canonical_name=canonical_name,
                canonical_name_normalized=normalized_name,
                entity_type=entity_type,
                description=description,
                discovery_method=DiscoveryMethod.USER_CREATED,
                confidence=1.0,
            )
            new_entity = await entity_repo.create(
                session, obj_in=entity_create
            )

            # Create canonical name as an alias (same pattern as classify)
            canonical_alias_create = EntityAliasCreate(
                entity_id=new_entity.id,
                alias_name=canonical_name,
                alias_name_normalized=normalized_name,
                alias_type=EntityAliasType.NAME_VARIANT,
                occurrence_count=0,
            )
            await alias_repo.create(session, obj_in=canonical_alias_create)

            alias_count = 1  # canonical name alias

            # Create additional aliases
            if alias:
                for alias_text in alias:
                    normalized_alias = normalizer.normalize(alias_text)
                    if normalized_alias is None:
                        console.print(
                            f"[yellow]Skipping alias '{alias_text}' "
                            f"(normalizes to empty).[/yellow]"
                        )
                        continue

                    alias_create = EntityAliasCreate(
                        entity_id=new_entity.id,
                        alias_name=alias_text,
                        alias_name_normalized=normalized_alias,
                        alias_type=EntityAliasType.NAME_VARIANT,
                        occurrence_count=0,
                    )
                    await alias_repo.create(session, obj_in=alias_create)
                    alias_count += 1

            await session.commit()

            # Display result
            details = (
                f"[bold]ID:[/bold] {new_entity.id}\n"
                f"[bold]Name:[/bold] {new_entity.canonical_name}\n"
                f"[bold]Type:[/bold] {new_entity.entity_type}\n"
                f"[bold]Description:[/bold] "
                f"{new_entity.description or '(none)'}\n"
                f"[bold]Aliases:[/bold] {alias_count}"
            )

            console.print(
                Panel(
                    details,
                    title="[green]Entity Created[/green]",
                    border_style="green",
                )
            )

    asyncio.run(_run())


@entity_app.command("list")
def list_entities(
    type_str: Optional[str] = typer.Option(
        None,
        "--type",
        help="Filter by entity type.",
    ),
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum number of entities to show."
    ),
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-q",
        help="Search by canonical name (case-insensitive).",
    ),
) -> None:
    """List named entities in a table."""

    async def _run() -> None:
        # Validate entity type filter if provided
        parsed_type: Optional[EntityType] = None
        if type_str is not None:
            try:
                parsed_type = EntityType(type_str)
            except ValueError:
                valid_types = ", ".join(t.value for t in EntityType)
                console.print(
                    Panel(
                        f"[red]Invalid entity type '{type_str}'. "
                        f"Valid values: {valid_types}[/red]",
                        title="Invalid --type",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

        async for session in db_manager.get_session(echo=False):
            # Build query
            query = select(NamedEntityDB).where(
                NamedEntityDB.status == "active"
            )

            if parsed_type is not None:
                query = query.where(
                    NamedEntityDB.entity_type == parsed_type.value
                )

            if search is not None:
                query = query.where(
                    NamedEntityDB.canonical_name.ilike(f"%{search}%")
                )

            query = query.order_by(NamedEntityDB.canonical_name.asc())
            query = query.limit(limit)

            result = await session.execute(query)
            entities = list(result.scalars().all())

            # Total count query
            count_query = select(func.count(NamedEntityDB.id)).where(
                NamedEntityDB.status == "active"
            )
            if parsed_type is not None:
                count_query = count_query.where(
                    NamedEntityDB.entity_type == parsed_type.value
                )
            if search is not None:
                count_query = count_query.where(
                    NamedEntityDB.canonical_name.ilike(f"%{search}%")
                )
            total_result = await session.execute(count_query)
            total_count = total_result.scalar() or 0

            if not entities:
                console.print(
                    Panel(
                        "[yellow]No entities found matching the criteria.[/yellow]",
                        title="No Entities",
                        border_style="yellow",
                    )
                )
                return

            # Build table
            entity_table = Table(
                title="Named Entities",
                show_header=True,
                header_style="bold blue",
            )
            entity_table.add_column("ID", style="dim", width=10)
            entity_table.add_column("Name", style="cyan", width=30)
            entity_table.add_column("Type", style="magenta", width=16)
            entity_table.add_column("Description", style="white", width=50)
            entity_table.add_column("Aliases", style="green", width=8)
            entity_table.add_column("Created", style="dim", width=12)

            for entity in entities:
                # Get alias count
                alias_count_result = await session.execute(
                    select(func.count(EntityAliasDB.id)).where(
                        EntityAliasDB.entity_id == entity.id
                    )
                )
                alias_count = alias_count_result.scalar() or 0

                # Truncate values for display
                short_id = str(entity.id)[:8]
                desc = entity.description or ""
                short_desc = (desc[:47] + "...") if len(desc) > 50 else desc
                created = (
                    entity.created_at.strftime("%Y-%m-%d")
                    if entity.created_at
                    else ""
                )

                entity_table.add_row(
                    short_id,
                    entity.canonical_name,
                    entity.entity_type,
                    short_desc,
                    str(alias_count),
                    created,
                )

            console.print(entity_table)
            console.print(
                f"\nShowing {len(entities)} of {total_count} total entities"
            )

    asyncio.run(_run())


@entity_app.command("backfill-descriptions")
def backfill_descriptions(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        is_flag=True,
        help="Preview which entities would be updated without writing.",
    ),
) -> None:
    """Copy classify --reason text into named_entities.description for entities with NULL descriptions."""

    async def _run() -> None:
        import uuid as uuid_mod

        async for session in db_manager.get_session(echo=False):
            # Find classify operations (operation_type='create') with a reason,
            # where the created entity still has description = NULL.
            # rollback_data->'created_entity_id' holds the entity UUID string.
            query = (
                select(
                    TagOperationLogDB.reason,
                    TagOperationLogDB.rollback_data["created_entity_id"].as_string().label(
                        "entity_id_str"
                    ),
                )
                .where(
                    TagOperationLogDB.operation_type == "create",
                    TagOperationLogDB.reason.isnot(None),
                    TagOperationLogDB.rolled_back.is_(False),
                    TagOperationLogDB.rollback_data["created_entity_id"].isnot(None),
                )
                .order_by(TagOperationLogDB.performed_at.asc())
            )
            result = await session.execute(query)
            rows = list(result.all())

            if not rows:
                console.print(
                    Panel(
                        "[yellow]No classify operations with reasons found.[/yellow]",
                        title="Nothing to Backfill",
                        border_style="yellow",
                    )
                )
                return

            updated = 0
            skipped = 0

            if dry_run:
                preview_table = Table(
                    title="Backfill Preview (dry run)",
                    show_header=True,
                    header_style="bold blue",
                )
                preview_table.add_column("Entity ID", style="dim", width=10)
                preview_table.add_column("Name", style="cyan", width=30)
                preview_table.add_column("Reason", style="white", width=50)

            for row in rows:
                entity_id_str = row.entity_id_str
                reason = row.reason

                if not entity_id_str or entity_id_str == "null":
                    skipped += 1
                    continue

                try:
                    entity_id = uuid_mod.UUID(entity_id_str)
                except ValueError:
                    skipped += 1
                    continue

                # Check if entity exists and has NULL description
                entity_result = await session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.id == entity_id,
                        NamedEntityDB.description.is_(None),
                    )
                )
                entity = entity_result.scalar_one_or_none()

                if entity is None:
                    skipped += 1
                    continue

                if dry_run:
                    preview_table.add_row(
                        str(entity.id)[:8],
                        entity.canonical_name,
                        reason[:50] if reason else "",
                    )
                else:
                    entity.description = reason
                    session.add(entity)

                updated += 1

            if dry_run:
                console.print(preview_table)
                console.print(
                    f"\n[bold]Dry run:[/bold] {updated} entities would be updated, "
                    f"{skipped} skipped"
                )
            else:
                await session.commit()
                console.print(
                    Panel(
                        f"[bold]Updated:[/bold] {updated} entities\n"
                        f"[bold]Skipped:[/bold] {skipped} (already has description, "
                        f"entity not found, or invalid ID)",
                        title="[green]Backfill Complete[/green]",
                        border_style="green",
                    )
                )

    asyncio.run(_run())
