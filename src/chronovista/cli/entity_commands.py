"""
Entity CLI commands for chronovista.

Commands for creating, browsing, and scanning named entities. Entities represent
real-world people, organizations, places, events, and other typed objects
discovered from or associated with video tags.

Feature 037 — Entity Classify Improvements (#69)
Feature 038 — Entity Mention Detection (scan command)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

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
from rich.table import Table
from sqlalchemy import func, select

from chronovista.config.database import db_manager
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
)
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
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
    "concept",
    "other",
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
            "event, work, technical_term, concept, other."
        ),
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Human-readable description of the entity.",
    ),
    alias: list[str] | None = typer.Option(
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
                    "person, organization, place, event, work, technical_term, concept, other",
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
            raise typer.Exit(code=1) from None

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


@entity_app.command("add-alias")
def add_alias(
    entity_name: str = typer.Argument(
        ..., help="Canonical name of the entity to add alias to."
    ),
    alias: list[str] = typer.Option(
        ...,
        "--alias",
        help="Alias name to add (repeatable).",
    ),
) -> None:
    """Add one or more aliases to an existing named entity."""

    async def _run() -> None:
        normalizer = TagNormalizationService()
        alias_repo = EntityAliasRepository()

        normalized_entity = normalizer.normalize(entity_name)
        if normalized_entity is None:
            console.print(
                Panel(
                    "[red]Entity name normalizes to empty string.[/red]",
                    title="Invalid Name",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        async for session in db_manager.get_session(echo=False):
            # Look up entity by normalized name
            result = await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_entity,
                )
            )
            entity = result.scalar_one_or_none()

            if entity is None:
                console.print(
                    Panel(
                        f"[red]No entity found with name '{entity_name}'.[/red]",
                        title="Entity Not Found",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1)

            added = 0
            skipped = 0

            for alias_text in alias:
                normalized_alias = normalizer.normalize(alias_text)
                if normalized_alias is None:
                    console.print(
                        f"[yellow]Skipping alias '{alias_text}' "
                        f"(normalizes to empty).[/yellow]"
                    )
                    skipped += 1
                    continue

                # Check for duplicate alias on this entity
                existing = await session.execute(
                    select(EntityAliasDB).where(
                        EntityAliasDB.entity_id == entity.id,
                        EntityAliasDB.alias_name_normalized == normalized_alias,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    console.print(
                        f"[yellow]Alias '{alias_text}' already exists "
                        f"for '{entity.canonical_name}', skipping.[/yellow]"
                    )
                    skipped += 1
                    continue

                alias_create = EntityAliasCreate(
                    entity_id=entity.id,
                    alias_name=alias_text,
                    alias_name_normalized=normalized_alias,
                    alias_type=EntityAliasType.NAME_VARIANT,
                    occurrence_count=0,
                )
                await alias_repo.create(session, obj_in=alias_create)
                added += 1

            await session.commit()

            details = (
                f"[bold]Entity:[/bold] {entity.canonical_name}\n"
                f"[bold]Type:[/bold] {entity.entity_type}\n"
                f"[bold]Aliases added:[/bold] {added}\n"
                f"[bold]Skipped:[/bold] {skipped}"
            )

            if added > 0:
                console.print(
                    Panel(
                        details,
                        title="[green]Alias(es) Added[/green]",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        details,
                        title="[yellow]No Aliases Added[/yellow]",
                        border_style="yellow",
                    )
                )

    asyncio.run(_run())


@entity_app.command("list")
def list_entities(
    type_str: str | None = typer.Option(
        None,
        "--type",
        help="Filter by entity type.",
    ),
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum number of entities to show."
    ),
    search: str | None = typer.Option(
        None,
        "--search",
        "-q",
        help="Search by canonical name (case-insensitive).",
    ),
    has_mentions: Annotated[
        bool,
        typer.Option("--has-mentions", help="Show only entities with mentions"),
    ] = False,
    no_mentions: Annotated[
        bool,
        typer.Option("--no-mentions", help="Show only entities without mentions"),
    ] = False,
    sort: Annotated[
        str | None,
        typer.Option("--sort", help="Sort by: name (default), mentions"),
    ] = None,
) -> None:
    """List named entities in a table."""

    # Validate mutually exclusive flags
    if has_mentions and no_mentions:
        console.print(
            Panel(
                "[red]Cannot use --has-mentions and --no-mentions together.[/red]",
                title="Invalid Options",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    async def _run() -> None:
        # Validate entity type filter if provided
        parsed_type: EntityType | None = None
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
                raise typer.Exit(code=1) from None

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

            if has_mentions:
                query = query.where(NamedEntityDB.mention_count > 0)
            if no_mentions:
                query = query.where(NamedEntityDB.mention_count == 0)

            if sort == "mentions":
                query = query.order_by(
                    NamedEntityDB.mention_count.desc(),
                    NamedEntityDB.canonical_name.asc(),
                )
            else:
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
            if has_mentions:
                count_query = count_query.where(
                    NamedEntityDB.mention_count > 0
                )
            if no_mentions:
                count_query = count_query.where(
                    NamedEntityDB.mention_count == 0
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
            entity_table.add_column("Exclusions", style="red", justify="right", width=10)
            entity_table.add_column(
                "Mentions", style="yellow", justify="right", width=10
            )
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

                exclusion_count = len(entity.exclusion_patterns or [])

                entity_table.add_row(
                    short_id,
                    entity.canonical_name,
                    entity.entity_type,
                    short_desc,
                    str(alias_count),
                    str(exclusion_count) if exclusion_count else "-",
                    f"{entity.mention_count:,}"
                    if entity.mention_count
                    else "0",
                    created,
                )

            console.print(entity_table)
            console.print(
                f"\nShowing {len(entities)} of {total_count} total entities"
            )

    asyncio.run(_run())


@entity_app.command("add-exclusion")
def add_exclusion(
    entity_name: str = typer.Argument(
        ..., help="Canonical name of the entity to add exclusion pattern(s) to."
    ),
    pattern: list[str] = typer.Option(
        ...,
        "--pattern",
        help="Exclusion pattern to add (repeatable).",
    ),
) -> None:
    """Add one or more exclusion patterns to a named entity.

    Exclusion patterns prevent false-positive matches during entity mention
    detection. For example, adding 'New Mexico' as an exclusion on the 'Mexico'
    entity ensures that 'New Mexico' segments are not counted as mentions of Mexico.
    """

    async def _run() -> None:
        normalizer = TagNormalizationService()
        normalized_entity = normalizer.normalize(entity_name)

        if normalized_entity is None:
            console.print(
                Panel(
                    "[red]Entity name normalizes to empty string.[/red]",
                    title="Invalid Name",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        async for session in db_manager.get_session(echo=False):
            # Look up entity by normalized canonical name (case-insensitive)
            result = await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_entity,
                )
            )
            entity = result.scalar_one_or_none()

            if entity is None:
                console.print(
                    f'[red]Error: Entity "{entity_name}" not found[/red]'
                )
                raise typer.Exit(code=1)

            # Validate all patterns before mutating state
            for pat in pattern:
                trimmed = pat.strip()
                if not trimmed:
                    console.print(
                        "[red]Error: Exclusion pattern must not be empty[/red]"
                    )
                    raise typer.Exit(code=1)
                if len(trimmed) > 500:
                    console.print(
                        "[red]Error: Exclusion pattern exceeds 500 character limit[/red]"
                    )
                    raise typer.Exit(code=1)

            # Build updated list, checking for duplicates
            current_patterns: list[str] = list(entity.exclusion_patterns or [])

            if len(current_patterns) >= 10:
                console.print(
                    f'[yellow]Warning: Entity "{entity.canonical_name}" already has '
                    f"{len(current_patterns)} exclusion patterns. Consider reviewing "
                    f"whether all patterns are still necessary.[/yellow]"
                )

            added_patterns: list[str] = []
            for pat in pattern:
                trimmed = pat.strip()
                if trimmed in current_patterns:
                    console.print(
                        f'[yellow]Warning: Pattern "{trimmed}" already exists '
                        f'on entity "{entity.canonical_name}"[/yellow]'
                    )
                    continue
                current_patterns.append(trimmed)
                added_patterns.append(trimmed)

            if added_patterns:
                entity.exclusion_patterns = current_patterns
                session.add(entity)
                await session.commit()

                for trimmed in added_patterns:
                    console.print(
                        f'Added exclusion pattern "{trimmed}" to entity '
                        f'"{entity.canonical_name}"'
                    )
                console.print(
                    f'Entity "{entity.canonical_name}" now has '
                    f"{len(current_patterns)} exclusion pattern(s)"
                )
            else:
                console.print(
                    f'[yellow]No new exclusion patterns added to '
                    f'"{entity.canonical_name}".[/yellow]'
                )

    asyncio.run(_run())


@entity_app.command("remove-exclusion")
def remove_exclusion(
    entity_name: str = typer.Argument(
        ..., help="Canonical name of the entity to remove an exclusion pattern from."
    ),
    pattern: str = typer.Option(
        ...,
        "--pattern",
        help="Exclusion pattern to remove.",
    ),
) -> None:
    """Remove an exclusion pattern from a named entity."""

    async def _run() -> None:
        normalizer = TagNormalizationService()
        normalized_entity = normalizer.normalize(entity_name)

        if normalized_entity is None:
            console.print(
                Panel(
                    "[red]Entity name normalizes to empty string.[/red]",
                    title="Invalid Name",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

        async for session in db_manager.get_session(echo=False):
            # Look up entity by normalized canonical name (case-insensitive)
            result = await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_entity,
                )
            )
            entity = result.scalar_one_or_none()

            if entity is None:
                console.print(
                    f'[red]Error: Entity "{entity_name}" not found[/red]'
                )
                raise typer.Exit(code=1)

            trimmed = pattern.strip()
            current_patterns: list[str] = list(entity.exclusion_patterns or [])

            if trimmed not in current_patterns:
                console.print(
                    f'[yellow]Warning: Pattern "{trimmed}" not found '
                    f'on entity "{entity.canonical_name}"[/yellow]'
                )
                return

            current_patterns.remove(trimmed)
            entity.exclusion_patterns = current_patterns
            session.add(entity)
            await session.commit()

            console.print(
                f'Removed exclusion pattern "{trimmed}" from entity '
                f'"{entity.canonical_name}"'
            )
            console.print(
                f'Entity "{entity.canonical_name}" now has '
                f"{len(current_patterns)} exclusion pattern(s)"
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


@entity_app.command("scan")
def scan_entities(
    entity_type: Annotated[
        str | None,
        typer.Option("--entity-type", help="Filter by entity type"),
    ] = None,
    video_id: Annotated[
        list[str] | None,
        typer.Option("--video-id", help="Filter by video ID (repeatable)"),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option("--language", help="Filter by language code"),
    ] = None,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", help="Segments per batch", min=100, max=5000),
    ] = 500,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing"),
    ] = False,
    full: Annotated[
        bool,
        typer.Option("--full", help="Delete and rescan all"),
    ] = False,
    new_entities_only: Annotated[
        bool,
        typer.Option("--new-entities-only", help="Scan only new entities"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Dry-run preview row limit"),
    ] = 50,
    audit: Annotated[
        bool,
        typer.Option(
            "--audit",
            help="Report user-correction mentions with unregistered text forms",
        ),
    ] = False,
    entity_id: Annotated[
        str | None,
        typer.Option("--entity-id", help="Scan for a single entity"),
    ] = None,
) -> None:
    """Scan transcript segments for named entity mentions."""

    # Validate mutual exclusivity: --audit and --full
    if audit and full:
        raise typer.BadParameter("--audit and --full are mutually exclusive")

    # Validate entity type if provided
    if entity_type is not None:
        try:
            EntityType(entity_type)
        except ValueError:
            valid_types = ", ".join(t.value for t in EntityType)
            console.print(
                Panel(
                    f"[red]Invalid entity type '{entity_type}'. "
                    f"Valid values: {valid_types}[/red]",
                    title="Invalid --entity-type",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1) from None

    # Validate --entity-id UUID format if provided
    parsed_entity_uuid: uuid.UUID | None = None
    if entity_id is not None:
        try:
            parsed_entity_uuid = uuid.UUID(entity_id)
        except ValueError:
            console.print(
                Panel(
                    f"[red]Invalid value: {entity_id!r}\n"
                    f"Expected UUID format, e.g. 550e8400-e29b-41d4-a716-446655440000[/red]",
                    title="Invalid --entity-id",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1) from None

    session_factory = db_manager.get_session_factory()
    service = EntityMentionScanService(session_factory=session_factory)

    async def _run() -> None:
        if audit:
            # Audit mode: report unregistered mention texts (read-only)
            audit_results = await service.audit_unregistered_mentions()

            if not audit_results:
                console.print(
                    "[green]No unregistered mention texts found.[/green]"
                )
                return

            audit_table = Table(
                title="Unregistered Mention Texts",
                show_header=True,
                header_style="bold blue",
            )
            audit_table.add_column("Entity", style="cyan", width=28)
            audit_table.add_column("Mention Text", style="green", width=28)
            audit_table.add_column(
                "Segment Count", style="yellow", justify="right", width=14
            )
            audit_table.add_column("Suggestion", style="dim", width=60)

            entity_ids_seen: set[str] = set()
            for canonical_name, entity_id, mention_text, segment_count in audit_results:
                entity_ids_seen.add(str(entity_id))
                suggestion = (
                    f'chronovista entities add-alias "{canonical_name}" '
                    f'--alias "{mention_text}"'
                )
                audit_table.add_row(
                    canonical_name,
                    mention_text,
                    str(segment_count),
                    suggestion,
                )

            console.print(audit_table)
            console.print(
                f"\nFound {len(audit_results)} unregistered mention text(s) "
                f"across {len(entity_ids_seen)} entity(ies)."
            )
            return

        # Resolve --entity-id: validate existence and status, then set scan params
        effective_entity_type: str | None = entity_type
        effective_new_entities_only: bool = new_entities_only
        effective_entity_ids: list[uuid.UUID] | None = None

        if parsed_entity_uuid is not None:
            async for session in db_manager.get_session(echo=False):
                db_entity = await session.get(NamedEntityDB, parsed_entity_uuid)
                if db_entity is None:
                    console.print(
                        Panel(
                            f"[red]No entity found with ID {parsed_entity_uuid}[/red]",
                            title="Entity not found",
                            border_style="red",
                        )
                    )
                    raise typer.Exit(code=1)
                if db_entity.status != "active":
                    console.print(
                        Panel(
                            f"[red]Entity is not active (status: {db_entity.status})[/red]",
                            title="Entity is not active",
                            border_style="red",
                        )
                    )
                    raise typer.Exit(code=1)
            effective_entity_type = None
            effective_new_entities_only = False
            effective_entity_ids = [parsed_entity_uuid]

        if dry_run:
            # Dry-run mode: show preview table
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Scanning (dry run)...", total=None)

                result = await service.scan(
                    entity_type=effective_entity_type,
                    video_ids=video_id,
                    language_code=language,
                    batch_size=batch_size,
                    dry_run=True,
                    full_rescan=full,
                    new_entities_only=effective_new_entities_only,
                    limit=limit,
                    entity_ids=effective_entity_ids,
                )

            if not result.dry_run_matches:
                console.print(
                    "[yellow]No entity mentions found matching the criteria.[/yellow]"
                )
                raise typer.Exit(code=0)

            preview_table = Table(
                title="Entity Mention Scan Preview (dry run)",
                show_header=True,
                header_style="bold blue",
            )
            preview_table.add_column("video_id", style="dim", width=14)
            preview_table.add_column("segment_id", style="dim", width=12)
            preview_table.add_column("start_time", style="dim", width=10)
            preview_table.add_column("entity_name", style="cyan", width=24)
            preview_table.add_column("entity_type", style="magenta", width=16)
            preview_table.add_column("matched_text", style="green", width=20)
            preview_table.add_column("context", style="white", width=40)

            for match in result.dry_run_matches:
                context_text = match.get("context", "")
                if len(context_text) > 40:
                    context_text = context_text[:37] + "..."

                preview_table.add_row(
                    match["video_id"],
                    str(match["segment_id"]),
                    f"{match['start_time']:.1f}",
                    match["entity_name"],
                    match["entity_type"],
                    match["matched_text"],
                    context_text,
                )

            console.print(preview_table)
            dry_run_summary = (
                f"\nDry run complete: [bold]{result.mentions_found:,}[/bold] mentions "
                f"would be created across [bold]{result.unique_videos:,}[/bold] videos "
                f"for [bold]{result.unique_entities:,}[/bold] entities "
                f"({result.segments_scanned:,} segments scanned, "
                f"{result.duration_seconds:.1f}s)"
            )
            if result.skipped_longest_match > 0 or result.skipped_exclusion_pattern > 0:
                dry_run_summary += (
                    f"\nSkipped (exclusion patterns): {result.skipped_exclusion_pattern:,}"
                    f"  |  Skipped (longest-match-wins): {result.skipped_longest_match:,}"
                )
            console.print(dry_run_summary)
        else:
            # Live mode: scan with progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Scanning segments...", total=None)

                def _progress_callback(scanned: int, found: int) -> None:
                    progress.update(
                        task,
                        completed=scanned,
                        description=f"Scanning segments... ({found:,} mentions found)",
                    )

                result = await service.scan(
                    entity_type=effective_entity_type,
                    video_ids=video_id,
                    language_code=language,
                    batch_size=batch_size,
                    dry_run=False,
                    full_rescan=full,
                    new_entities_only=effective_new_entities_only,
                    progress_callback=_progress_callback,
                    entity_ids=effective_entity_ids,
                )

            # Summary panel
            summary_lines = [
                f"[bold]Segments scanned:[/bold] {result.segments_scanned:,}",
                f"[bold]Mentions found:[/bold] {result.mentions_found:,}",
                f"[bold]Mentions skipped:[/bold] {result.mentions_skipped:,}",
                f"[bold]Skipped (exclusion patterns):[/bold] {result.skipped_exclusion_pattern:,}",
                f"[bold]Skipped (longest-match-wins):[/bold] {result.skipped_longest_match:,}",
                f"[bold]Unique entities:[/bold] {result.unique_entities:,}",
                f"[bold]Unique videos:[/bold] {result.unique_videos:,}",
                f"[bold]Duration:[/bold] {result.duration_seconds:.1f}s",
            ]
            if result.failed_batches > 0:
                summary_lines.append(
                    f"[bold red]Failed batches:[/bold red] {result.failed_batches:,}"
                )

            border = "green" if result.failed_batches == 0 else "yellow"
            title = (
                "[green]Scan Complete[/green]"
                if result.failed_batches == 0
                else "[yellow]Scan Complete (with failures)[/yellow]"
            )

            console.print(
                Panel(
                    "\n".join(summary_lines),
                    title=title,
                    border_style=border,
                )
            )

    asyncio.run(_run())


@entity_app.command("stats")
def entity_stats(
    entity_type: Annotated[
        str | None,
        typer.Option("--entity-type", help="Filter statistics by entity type."),
    ] = None,
    top: Annotated[
        int,
        typer.Option("--top", help="Number of top entities to display."),
    ] = 10,
) -> None:
    """Display aggregate entity mention statistics."""

    async def _run() -> None:
        # Validate entity type if provided
        if entity_type is not None:
            try:
                EntityType(entity_type)
            except ValueError:
                valid_types = ", ".join(t.value for t in EntityType)
                console.print(
                    Panel(
                        f"[red]Invalid entity type '{entity_type}'. "
                        f"Valid values: {valid_types}[/red]",
                        title="Invalid --entity-type",
                        border_style="red",
                    )
                )
                raise typer.Exit(code=1) from None

        repo = EntityMentionRepository()

        async for session in db_manager.get_session(echo=False):
            stats = await repo.get_statistics(session, entity_type=entity_type)

            # Overview panel
            filter_note = (
                f"\n[bold]Filter:[/bold] entity_type = {entity_type}"
                if entity_type is not None
                else ""
            )
            overview = (
                f"[bold]Total mentions:[/bold] {stats['total_mentions']:,}\n"
                f"[bold]Entities with mentions:[/bold] "
                f"{stats['unique_entities_with_mentions']:,} / {stats['total_entities']:,}\n"
                f"[bold]Videos with mentions:[/bold] {stats['unique_videos_with_mentions']:,}\n"
                f"[bold]Coverage:[/bold] {stats['coverage_pct']:.1f}%"
                f"{filter_note}"
            )
            console.print(
                Panel(
                    overview,
                    title="Entity Mention Statistics",
                    border_style="blue",
                )
            )

            # Type breakdown table
            if stats["type_breakdown"]:
                type_table = Table(
                    title="By Entity Type",
                    show_header=True,
                    header_style="bold blue",
                )
                type_table.add_column("Type", style="magenta", width=20)
                type_table.add_column(
                    "Entities", style="green", justify="right", width=10
                )
                type_table.add_column(
                    "Mentions", style="cyan", justify="right", width=12
                )
                for tb in stats["type_breakdown"]:
                    type_table.add_row(
                        tb["entity_type"],
                        str(tb["entity_count"]),
                        f"{tb['mention_count']:,}",
                    )
                console.print(type_table)

            # Top entities table
            top_entities = stats["top_entities"][:top]
            if top_entities:
                top_table = Table(
                    title=f"Top {len(top_entities)} Entities by Video Count",
                    show_header=True,
                    header_style="bold blue",
                )
                top_table.add_column("Name", style="cyan", width=30)
                top_table.add_column("Type", style="magenta", width=16)
                top_table.add_column(
                    "Mentions", style="green", justify="right", width=10
                )
                top_table.add_column(
                    "Videos", style="yellow", justify="right", width=10
                )
                for ent in top_entities:
                    top_table.add_row(
                        ent["canonical_name"],
                        ent["entity_type"],
                        f"{ent['mention_count']:,}",
                        f"{ent['video_count']:,}",
                    )
                console.print(top_table)

            if not stats["type_breakdown"] and not top_entities:
                console.print(
                    Panel(
                        "[yellow]No entity mentions found. "
                        "Run 'entities scan' first.[/yellow]",
                        title="No Data",
                        border_style="yellow",
                    )
                )

    asyncio.run(_run())
