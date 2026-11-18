"""CLI commands for the connection explorer (Feature 112).

``chronovista graph`` groups the dev-scoped graph commands. The engine is read-only and
connects lazily; when the graph is unavailable the commands degrade with a clear message
rather than a traceback (FR-009).
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from chronovista.container import container
from chronovista.graph import GraphUnavailableError
from chronovista.models.graph_connection import (
    ConnectionChain,
    ConnectionKind,
    GraphConnection,
    GraphNode,
)
from chronovista.repositories.neo4j_graph_repository import EntityNotInGraphError
from chronovista.services.connection_service import AmbiguousEntityError

console = Console()

app = typer.Typer(
    name="graph",
    help="🕸️ Explore connections between entities in the dev-scoped graph.",
    no_args_is_help=True,
)

# Human label per connection kind (declared in by-kind order to match the enum).
_KIND_LABEL: dict[ConnectionKind, str] = {
    ConnectionKind.ASSERTED: "asserted",
    ConnectionKind.SHARED_REFERENT: "shared affiliation",
    ConnectionKind.SHARED_CATEGORY: "shared category",
    ConnectionKind.CO_OCCURRENCE_TRANSCRIPT: "discussed alongside (transcript)",
    ConnectionKind.CO_OCCURRENCE_TITLEDESC: "billed together (title/description)",
    ConnectionKind.CO_OCCURRENCE_TAGS: "co-creates content (tags)",
    ConnectionKind.CO_OCCURRENCE_MANUAL: "hand-linked (manual)",
}


@app.callback()
def graph() -> None:
    """Explore how entities are connected in the dev-scoped graph."""


@app.command()
def connect(
    a: str = typer.Argument(..., help="First entity: an exact name or an entity id"),
    b: str = typer.Argument(..., help="Second entity: an exact name or an entity id"),
    max_hops: int = typer.Option(
        4, "--max-hops", help="Hop budget for the asserted tier"
    ),
    max_category_size: int | None = typer.Option(
        None,
        "--max-category-size",
        help="Named tractability bound on a shared category's global size (default: no cut)",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the raw result as JSON"),
) -> None:
    """Show how two entities connect — one line per connection kind, reviewed verdict if any."""
    asyncio.run(_connect(a, b, max_hops, max_category_size, json_out))


async def _connect(
    a: str,
    b: str,
    max_hops: int,
    max_category_size: int | None,
    json_out: bool,
) -> None:
    service = container.create_connection_service()
    try:
        node_a = await service.resolve(a)
        node_b = await service.resolve(b)
        if node_a.entity_id is None or node_b.entity_id is None:
            console.print("[red]resolved to a non-entity node[/red]")
            raise typer.Exit(1)
        result = await service.connect(
            node_a.entity_id,
            node_b.entity_id,
            max_hops=max_hops,
            max_category_size=max_category_size,
        )
    except GraphUnavailableError as exc:
        console.print(f"[red]Graph unavailable:[/red] {exc}")
        console.print(
            "[dim]Start it with: "
            "docker compose -f docker-compose.dev.yml --profile graph up -d neo4j-dev[/dim]"
        )
        raise typer.Exit(1) from exc
    except AmbiguousEntityError as exc:
        console.print(
            f"[yellow]'{exc.token}' matches {len(exc.matches)} entities — "
            "pick one by id:[/yellow]"
        )
        for match in exc.matches[:10]:
            console.print(f"  [cyan]{match.entity_id}[/cyan]  {match.name}")
        raise typer.Exit(1) from exc
    except EntityNotInGraphError as exc:
        console.print(f"[yellow]Not found:[/yellow] {exc}")
        raise typer.Exit(1) from exc
    finally:
        await container.neo4j_client.close()

    if json_out:
        console.print_json(result.model_dump_json())
    else:
        _render(node_a, node_b, result)


def _render(node_a: GraphNode, node_b: GraphNode, result: GraphConnection) -> None:
    console.print(f"[bold]{node_a.name}[/bold]  ↔  [bold]{node_b.name}[/bold]")
    verdict = result.reviewed_verdict
    if verdict is not None and verdict.verdict == "relationship":
        console.print(
            f"  [green]✓ reviewed relationship[/green]: {verdict.relation} "
            f"[dim]({verdict.confidence} confidence)[/dim]"
        )
    elif (
        verdict is not None
        and verdict.verdict == "coincidence"
        and verdict.confidence == "high"
    ):
        # Say WHY co-occurrence is absent: a human reviewed the pair as coincidental.
        console.print(
            "  [dim]⚑ reviewed as coincidental — co-occurrence suppressed[/dim]"
        )
    # Position is a by-kind precedence, not a strength ranking: the per-line scores use
    # different references across tiers (ln(entity_count/degree) vs ln(1e6/globalSize)), so a
    # score ranks within its kind only — never read one kind's score against another's.
    if sum(1 for chain in result.chains if chain.score is not None) >= 2:
        console.print(
            "  [dim]listed by connection kind; a score ranks within its kind, not across[/dim]"
        )
    for chain in result.chains:
        if chain.kind.value.startswith("co_occurrence_"):
            continue  # rendered as a group below (order is not a strength ranking)
        label = _KIND_LABEL.get(chain.kind, chain.kind.value)
        if chain.kind is ConnectionKind.ASSERTED:
            # A chain is scored by its weakest hub; a mega-hub transit reads "non-specific"
            # (like a universal category) rather than silently ranking first unqualified.
            console.print(
                f"  [magenta]{label}[/magenta]: {_format_path(node_a, chain)} "
                f"[dim]({_specificity_label(chain)})[/dim]"
            )
        elif chain.kind is ConnectionKind.SHARED_CATEGORY and chain.steps:
            category = chain.steps[0].to_node.name
            console.print(
                f"  [magenta]{label}[/magenta]: via «{category}» "
                f"[dim]({_specificity_label(chain)})[/dim]"
            )
        elif chain.kind is ConnectionKind.SHARED_REFERENT and len(chain.steps) == 2:
            referent = chain.steps[0].to_node.name
            # convergent (step0 forward: a→m, b→m) ⇒ "both → X"; divergent ⇒ "X → both".
            body = (
                f"both → «{referent}»"
                if chain.steps[0].forward
                else f"«{referent}» → both"
            )
            # Name BOTH legs: the a-leg (t1) and b-leg (t2) often differ, and collapsing two
            # unlike relations into one implied type is the provenance-collapse this guards.
            t1, t2 = chain.steps[0].edge_type, chain.steps[1].edge_type
            relations = t1 if t1 == t2 else f"{t1} / {t2}"
            console.print(
                f"  [magenta]{label}[/magenta]: {body} "
                f"[dim]({relations}, {_specificity_label(chain)})[/dim]"
            )
        else:
            console.print(
                f"  [magenta]{label}[/magenta]: {_format_path(node_a, chain)}"
            )
    # Co-occurrence is four DISTINCT presence channels; their order is enum/presentation
    # order, NOT a strength ranking (§9.5). Say so when more than one is present.
    co_chains = [c for c in result.chains if c.kind.value.startswith("co_occurrence_")]
    if len(co_chains) >= 2:
        console.print(
            "  [dim]co-occurrence (distinct channels, listed by type — not ranked):[/dim]"
        )
    for chain in co_chains:
        label = _KIND_LABEL.get(chain.kind, chain.kind.value)
        console.print(f"  [magenta]{label}[/magenta]: {_format_path(node_a, chain)}")
    # Attribute the absence of a KB chain/referent to coverage (FR-016), not non-relationship.
    kinds = {chain.kind for chain in result.chains}
    if (
        ConnectionKind.ASSERTED not in kinds
        and ConnectionKind.SHARED_REFERENT not in kinds
    ):
        _render_kb_gap(
            node_a,
            node_b,
            # A coincidence verdict is a negative, not an "other" connection — only a
            # relationship verdict or a surviving chain counts as a real connection here.
            has_other=bool(result.chains)
            or (verdict is not None and verdict.verdict == "relationship"),
            max_hops=result.searched_max_hops,
        )


def _render_kb_gap(
    a: GraphNode, b: GraphNode, *, has_other: bool, max_hops: int
) -> None:
    """Attribute "no KB path" to endpoint coverage vs a stated non-relationship (FR-016).

    The asserted search is bounded by ``max_hops``, so an absence is "within N hops", never
    absolute (FR-007a); when nothing connects at all it is "no meaningful connection" (FR-007).
    """
    prefix = (
        f"no asserted KB path within {max_hops} hops"
        if has_other
        else f"no meaningful connection (searched within {max_hops} hops)"
    )
    da, db = a.kb_degree, b.kb_degree
    if da is None or db is None:
        console.print(f"  [dim]{prefix}.[/dim]")
        return
    console.print(
        f"  [dim]{prefix} — KB coverage: «{a.name}» {da}, «{b.name}» {db} edges[/dim]"
    )
    low_name, low_deg = (a.name, da) if da <= db else (b.name, db)
    if low_deg < 3:
        console.print(
            f"  [yellow]↳ «{low_name}» is barely in the knowledge base — likely an "
            "enrichment gap, not a stated non-relationship[/yellow]"
        )


def _specificity_label(chain: ConnectionChain) -> str:
    """ "non-specific" when a scored chain floors to 0 (universal), else "score X.X"."""
    score = chain.score if chain.score is not None else 0.0
    return "non-specific" if score <= 0.0 else f"score {score:.1f}"


def _format_path(node_a: GraphNode, chain: ConnectionChain) -> str:
    parts = [node_a.name]
    for step in chain.steps:
        arrow = f"—[{step.edge_type}]→" if step.forward else f"←[{step.edge_type}]—"
        parts.append(f"{arrow} {step.to_node.name}")
    return " ".join(parts)
