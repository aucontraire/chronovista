"""Relationship-candidate generation CLI (Feature 107).

Operator command to (re)generate the novel-relationship candidate queue. Generation
is the only writer; the API and frontend are read-only. ``--dry-run`` computes and
reports counts but writes nothing (the run is rolled back, leaving no trace and no
lingering 'running' lock).
"""

from __future__ import annotations

import asyncio
from enum import Enum

import typer
from rich.console import Console

from chronovista.services.relationship_candidate_service import (
    generate_relationship_candidates,
    generate_transcript_candidates,
)


class CandidateChannel(str, Enum):
    """Evidence channel a generation run reads."""

    TITLE_DESCRIPTION = "title_description"
    TRANSCRIPT = "transcript"


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
    channel: CandidateChannel = typer.Option(
        CandidateChannel.TITLE_DESCRIPTION,
        "--channel",
        help="Evidence channel to generate from: title_description (default) or transcript.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute and report counts, but write nothing (rolls back).",
    ),
) -> None:
    """Generate the novel-relationship candidate queue for an evidence channel.

    title_description (default): co-occurring entity pairs with lift >= 5 and
    support >= 5 and no typed Wikidata tie, ranked by lift. Re-running upserts in
    place (preserving row identity) and removes pairs that no longer qualify.

    transcript: pairs that co-occur in video transcripts, ranked by SUPPORT (shared
    videos), not lift. A run is additive and net-new only: it writes new candidates
    and never modifies or removes existing ones. Pairs already present as candidates
    are skipped ("deferred") for a later dual-signal merge.
    """
    if channel is CandidateChannel.TRANSCRIPT:
        transcript_summary = asyncio.run(
            generate_transcript_candidates(dry_run=dry_run)
        )
        _print_transcript_summary(transcript_summary, dry_run)
        return

    summary = asyncio.run(generate_relationship_candidates(dry_run=dry_run))
    console.print(f"[bold cyan]{_label(dry_run)}[/bold cyan]")
    console.print(f"  candidates written:          {summary['written']}")
    console.print(f"  candidates removed (stale):  {summary['removed']}")
    console.print(f"  channel video universe (N):  {summary['channel_video_universe']}")
    console.print(f"  corpus size (entities):      {summary.get('corpus_size', 0)}")


def _label(dry_run: bool) -> str:
    return "DRY RUN — nothing written" if dry_run else "Generation complete"


def _print_transcript_summary(summary: dict[str, int], dry_run: bool) -> None:
    console.print(f"[bold cyan]{_label(dry_run)}[/bold cyan]")
    console.print(f"  new candidates written:      {summary['written']}")
    console.print(f"  evidence rows (children):    {summary['children']}")
    console.print(
        f"  deferred (already present):  {summary['deferred']}"
        "  [dim]skipped for the later dual-signal merge[/dim]"
    )
    console.print(f"  channel video universe (N):  {summary['channel_video_universe']}")
    console.print(f"  corpus size (entities):      {summary.get('corpus_size', 0)}")
