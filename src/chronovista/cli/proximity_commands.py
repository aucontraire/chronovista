"""Transcript proximity primitive CLI (Feature 116).

Operator commands for the proximity computor. ``rebuild`` recomputes the instance
table + rollup — for the whole corpus, or scoped to ``--video-id`` / ``--entity-id``;
``drain`` processes the invalidation queue (``proximity_dirty_scopes``) that the
producer hooks fill. Generation is the only writer; the API and frontend are
read-only. ``--dry-run`` computes and reports counts but writes nothing (the run is
rolled back, leaving no trace and no lingering 'running' lock).
"""

from __future__ import annotations

import asyncio
import uuid

import typer
from rich.console import Console
from rich.panel import Panel

from chronovista.services.proximity_service import (
    drain_dirty_scopes,
    rebuild_proximity,
)

proximity_app = typer.Typer(
    help="🧲 Transcript proximity primitive (rebuild / drain).",
    no_args_is_help=True,
)
console = Console()


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        console.print(
            Panel(
                f"[red]'{raw}' is not a valid entity id (expected a UUID).[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1) from exc


@proximity_app.command("rebuild")
def rebuild(
    video_id: list[str] = typer.Option(
        [],
        "--video-id",
        help="Scope the rebuild to this video (repeatable). Omit for a full rebuild.",
    ),
    entity_id: list[str] = typer.Option(
        [],
        "--entity-id",
        help="Scope the rebuild to pairs touching this entity (repeatable).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute and report counts, but write nothing (rolls back).",
    ),
) -> None:
    """Recompute proximity instances + rollup (full, or scoped).

    With no ``--video-id`` / ``--entity-id`` this is a full rebuild. With a scope,
    only the matching instances are recomputed and only the affected pairs' rollup is
    rebuilt.
    """
    entity_uuids = [_parse_uuid(raw) for raw in entity_id]

    async def _run() -> dict[str, int]:
        return await rebuild_proximity(
            video_ids=video_id or None,
            entity_ids=entity_uuids or None,
            dry_run=dry_run,
        )

    try:
        summary = asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any failure cleanly
        console.print(Panel(f"[red]{exc}[/red]", title="Error", border_style="red"))
        raise typer.Exit(1) from exc

    full = not video_id and not entity_uuids
    scope = (
        "full corpus"
        if full
        else (f"{len(video_id)} video(s), {len(entity_uuids)} entity(ies)")
    )
    label = "DRY RUN — nothing written" if dry_run else "Rebuild complete"
    body = (
        f"scope:              {scope}\n"
        f"instances written:  {summary['instances_written']}\n"
        f"instances deleted:  {summary['instances_deleted']}\n"
        f"pairs rolled up:    {summary['pairs_rolled_up']}"
    )
    console.print(
        Panel(body, title=label, border_style="yellow" if dry_run else "green")
    )


@proximity_app.command("drain")
def drain(
    limit: int | None = typer.Option(
        None, "--limit", help="Process at most this many dirty scopes."
    ),
) -> None:
    """Recompute every queued dirty ``(video, language)`` scope, then clear it."""

    async def _run() -> dict[str, int]:
        return await drain_dirty_scopes(limit=limit)

    try:
        summary = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - surface any failure cleanly
        console.print(Panel(f"[red]{exc}[/red]", title="Error", border_style="red"))
        raise typer.Exit(1) from exc

    body = (
        f"scopes drained:     {summary['scopes_drained']}\n"
        f"instances written:  {summary['instances_written']}"
    )
    console.print(Panel(body, title="Drain complete", border_style="green"))
