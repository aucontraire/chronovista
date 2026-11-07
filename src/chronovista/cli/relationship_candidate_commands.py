"""Relationship-candidate generation CLI (Feature 107).

Operator command to (re)generate the novel-relationship candidate queue. Generation
is the only writer; the API and frontend are read-only. ``--dry-run`` computes and
reports counts but writes nothing (the run is rolled back, leaving no trace and no
lingering 'running' lock).
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from chronovista.services.relationship_candidate_service import (
    generate_relationship_candidates,
)

relationship_app = typer.Typer(
    help="🔗 Novel-relationship candidate queue (co-occur, no typed tie).",
    no_args_is_help=True,
)
console = Console()


@relationship_app.callback()
def _relationship_main() -> None:
    """Novel-relationship candidate queue (read-only MVP).

    A no-op group callback so Typer keeps the ``generate`` subcommand NAME rather
    than collapsing a single-command app (which would make the path
    ``candidates relationships`` instead of ``candidates relationships generate``).
    """


@relationship_app.command("generate")
def generate(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute and report counts, but write nothing (rolls back).",
    ),
) -> None:
    """Generate (or idempotently regenerate) the novel-relationship candidate queue.

    Co-occurring entity pairs on the title+description channel with lift >= 5 and
    support >= 5 and no typed Wikidata tie, ranked by lift. Re-running upserts in
    place (preserving row identity) and removes pairs that no longer qualify.
    """

    async def _run() -> dict[str, int]:
        return await generate_relationship_candidates(dry_run=dry_run)

    summary = asyncio.run(_run())
    label = "DRY RUN — nothing written" if dry_run else "Generation complete"
    console.print(f"[bold cyan]{label}[/bold cyan]")
    console.print(f"  candidates written:          {summary['written']}")
    console.print(f"  candidates removed (stale):  {summary['removed']}")
    console.print(f"  channel video universe (N):  {summary['channel_video_universe']}")
    console.print(f"  corpus size (entities):      {summary.get('corpus_size', 0)}")
