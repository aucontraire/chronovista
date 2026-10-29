"""
CLI commands for the seed-and-grow candidate suggestion queue (Feature 096).

``chronovista candidates`` — generate relationship-discovered entity candidates,
review the ranked pending queue, and approve/reject them. Approval creates a
grounded entity through the existing creation + enrichment path; this group owns
all mutating actions (the API surface is read-only).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.config.database import db_manager
from chronovista.models.enums import ReviewStatus, TriageCategory
from chronovista.repositories.app_identity_repository import AppIdentityRepository
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.candidate_suggestion_service import CandidateSuggestionService

candidate_app = typer.Typer(
    name="candidates",
    help="🌱 Seed-and-grow entity candidate queue",
    no_args_is_help=True,
)

console = Console()

_CHANNEL = "relation"


def _service(*, with_enrichment: bool = False) -> CandidateSuggestionService:
    """Construct the service with inline repositories (CLI does not use the DI container)."""
    enrichment = None
    if with_enrichment:
        from chronovista.services.entity_enrichment_service import (
            get_enrichment_service,
        )

        enrichment = get_enrichment_service()
    from chronovista.services.wikidata_client import WikidataClient

    return CandidateSuggestionService(
        candidate_repo=CandidateSuggestionRepository(),
        entity_repo=NamedEntityRepository(),
        video_repo=VideoRepository(),
        alias_repo=EntityAliasRepository(),
        enrichment=enrichment,
        # Authoritative P31 typing for generation + approval re-verification (Feature 098);
        # degrades to the relation heuristic / stored type when Wikidata is unreachable.
        wikidata_client=WikidataClient(),
    )


async def _reviewer(session: AsyncSession) -> str:
    """Resolve the canonical operator identity for a verdict (FR-006a), with a fallback."""
    identity = await AppIdentityRepository().get_identity(session)
    return identity.user_id if identity is not None else "cli-operator"


@candidate_app.command("generate")
def generate(
    channel: str = typer.Option(
        _CHANNEL, "--channel", help="Discovery channel (only 'relation' is implemented)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute and summarize without writing anything"
    ),
) -> None:
    """Discover, ground, score, and persist candidates from the current library."""

    async def run() -> None:
        async with db_manager.session() as session:
            summary = await _service().generate(session, dry_run=dry_run)

        if summary.empty_reason and summary.candidates_discovered == 0:
            console.print(
                Panel(
                    f"[yellow]{summary.empty_reason}[/yellow]",
                    title="Nothing to generate",
                    border_style="yellow",
                )
            )
            return

        triage = summary.by_triage
        body = (
            f"grounded seeds:        {summary.seeds_grounded}\n"
            f"candidates discovered: {summary.candidates_discovered}\n"
            f"upserted:              {summary.candidates_upserted}"
            f"{'  (dry run — not written)' if dry_run else ''}\n"
            f"superseded:            {summary.superseded}\n"
            f"pending total:         {summary.pending_total}\n"
            f"  worth-review:        {triage.get(TriageCategory.WORTH_REVIEW.value, 0)}\n"
            f"  likely-eliminable:   {triage.get(TriageCategory.LIKELY_ELIMINABLE.value, 0)}\n"
            f"  grounds-nowhere:     {triage.get(TriageCategory.GROUNDS_NOWHERE.value, 0)}"
        )
        console.print(Panel(body, title="Candidate generation", border_style="green"))

    _invoke(run)


@candidate_app.command("list")
def list_candidates(
    triage: str | None = typer.Option(
        None, "--triage", help="worth_review | likely_eliminable | grounds_nowhere"
    ),
    type_hint: str | None = typer.Option(None, "--type", help="Filter by type hint"),
    min_tokens: int | None = typer.Option(
        None, "--min-tokens", help="Hide names with fewer tokens (e.g. 2)"
    ),
    possible_duplicate: bool = typer.Option(
        False,
        "--possible-duplicate",
        help="Only candidates flagged as a possible duplicate",
    ),
    sort: str = typer.Option(
        "score", "--sort", help="score | corroboration | salience"
    ),
    limit: int = typer.Option(50, "--limit", help="Max rows to show"),
) -> None:
    """Show the ranked pending candidate queue."""

    async def run() -> None:
        async with db_manager.session() as session:
            rows, total = await CandidateSuggestionRepository().list_pending(
                session,
                source_channel=_CHANNEL,
                triage=triage,
                type_hint=type_hint,
                min_token_count=min_tokens,
                possible_duplicate=possible_duplicate if possible_duplicate else None,
                sort=sort,
                limit=limit,
            )

        table = Table(
            title=f"Pending candidates ({len(rows)} of {total})",
            show_header=True,
            header_style="bold blue",
        )
        for col in (
            "id",
            "label",
            "type",
            "toks",
            "sal",
            "corrob",
            "edges",
            "score",
            "triage",
            "dup",
        ):
            table.add_column(
                col,
                justify=(
                    "right"
                    if col in {"toks", "sal", "corrob", "edges", "score"}
                    else "left"
                ),
            )
        for r in rows:
            table.add_row(
                str(r.id)[:8],
                r.label,
                r.type_hint,
                str(r.token_count),
                str(r.salience),
                str(r.corroboration_count),
                str(r.dangling_edge_count),
                f"{r.score:.1f}",
                r.triage,
                "⚠" if r.possible_duplicate_of_id is not None else "",
            )
        console.print(table)

    _invoke(run)


@candidate_app.command("show")
def show(
    candidate_id: str = typer.Argument(
        ..., help="Candidate id (full or 8-char prefix shown by list)"
    )
) -> None:
    """Show full detail for one candidate."""

    async def run() -> None:
        cid = _parse_uuid(candidate_id)
        async with db_manager.session() as session:
            row = await CandidateSuggestionRepository().get(session, cid)
        if row is None:
            console.print(
                Panel(f"[red]No candidate {candidate_id}[/red]", border_style="red")
            )
            raise typer.Exit(1)
        provenance = row.provenance or {}
        body = (
            f"qid:          {row.wikidata_qid}\n"
            f"label:        {row.label}\n"
            f"type hint:    {row.type_hint}\n"
            f"tokens:       {row.token_count}\n"
            f"salience:     {row.salience}\n"
            f"corroboration:{row.corroboration_count}\n"
            f"dangling:     {row.dangling_edge_count}\n"
            f"score:        {row.score:.2f}\n"
            f"triage:       {row.triage}\n"
            f"status:       {row.review_status}\n"
            f"relations:    {', '.join(provenance.get('relations', []))}\n"
            f"seeds:        {len(provenance.get('seed_entity_ids', []))}\n"
            f"possible dup: {row.possible_duplicate_of_id or '-'}"
        )
        console.print(
            Panel(body, title=f"Candidate {str(row.id)[:8]}", border_style="blue")
        )

    _invoke(run)


@candidate_app.command("approve")
def approve(
    candidate_id: str = typer.Argument(..., help="Candidate id to approve")
) -> None:
    """Approve a candidate — creates a grounded entity via the existing path."""

    async def run() -> None:
        cid = _parse_uuid(candidate_id)
        async with db_manager.session() as session:
            reviewer = await _reviewer(session)
            result = await _service(with_enrichment=True).approve(
                session, candidate_id=cid, reviewed_by=reviewer
            )
        color = {"approved": "green", "superseded": "yellow"}.get(result.outcome, "red")
        body = f"outcome: {result.outcome}\n{result.detail or ''}"
        if result.created_entity_id is not None:
            body += f"\nentity:  {result.created_entity_id}"
        console.print(Panel(body, title="Approve", border_style=color))
        if result.outcome == "failed":
            raise typer.Exit(1)

    _invoke(run)


@candidate_app.command("reject")
def reject(
    candidate_id: str = typer.Argument(..., help="Candidate id to reject")
) -> None:
    """Reject a candidate — it is not re-offered on later runs."""

    async def run() -> None:
        cid = _parse_uuid(candidate_id)
        async with db_manager.session() as session:
            reviewer = await _reviewer(session)
            result = await _service().reject(
                session, candidate_id=cid, reviewed_by=reviewer
            )
        color = "green" if result.outcome == "rejected" else "red"
        console.print(
            Panel(
                f"outcome: {result.outcome}\n{result.detail or ''}",
                title="Reject",
                border_style=color,
            )
        )
        if result.outcome == "failed":
            raise typer.Exit(1)

    _invoke(run)


@candidate_app.command("summary")
def summary() -> None:
    """Show candidate counts by review status and (pending) triage bucket."""

    async def run() -> None:
        async with db_manager.session() as session:
            counts = await CandidateSuggestionRepository().counts_by_status(
                session, source_channel=_CHANNEL
            )
        table = Table(
            title="Candidate queue", show_header=True, header_style="bold blue"
        )
        table.add_column("metric")
        table.add_column("count", justify="right")
        for status in ReviewStatus:
            table.add_row(status.value, str(counts.get(status.value, 0)))
        for t in TriageCategory:
            table.add_row(f"pending · {t.value}", str(counts.get(t.value, 0)))
        console.print(table)

    _invoke(run)


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        console.print(
            Panel(
                f"[red]'{raw}' is not a full candidate id. Pass the full UUID "
                f"(the list view shows an 8-char prefix).[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1) from exc


def _invoke(run: Callable[[], Coroutine[Any, Any, None]]) -> None:
    try:
        asyncio.run(run())
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure cleanly
        console.print(Panel(f"[red]{exc}[/red]", title="Error", border_style="red"))
        raise typer.Exit(1) from exc
