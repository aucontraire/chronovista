"""Transcript proximity primitive CLI (Features 116, 117).

Operator commands for the proximity measurement. The API process keeps proximity
current on its own (a background worker recomputes every invalidated scope); these
commands are for building it in bulk, catching up without the API, and inspecting it.

- ``rebuild``: bring every scope (or the requested ones) current, resumably.
- ``drain``: process stale scopes now, like the worker does.
- ``retry-failed``: make failing scopes retry immediately.
- ``status``: counts by state, failing scopes, and whether a rebuild is running.

Exit codes (contracts/cli.md): 0 when the requested set is entirely current (or the
command completed), 1 on error or when another rebuild holds the lock, 75 when work
remains (failing, deferred, held elsewhere, or still pending). 75 is sysexits
EX_TEMPFAIL ("try again later"); 2 cannot be used, because Click already exits 2
for every usage error, so "re-run while incomplete" would loop on a typo.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from chronovista.models.entity_pair_proximity import ProcessSummary
from chronovista.services.proximity_service import (
    FAILING_ATTEMPTS,
    drain_stale_scopes,
    dry_run_proximity,
    proximity_status,
    rebuild_proximity,
    retry_failed,
)

proximity_app = typer.Typer(
    help=(
        "🧲 Transcript proximity: which entities are mentioned within 120 s of each "
        "other in a transcript. It is computed per (video, language) SCOPE; a scope "
        "is CURRENT when computed from its latest transcript and mentions, STALE when "
        "they changed since. The API keeps it current automatically."
    ),
    no_args_is_help=True,
)
console = Console()

EXIT_INCOMPLETE = 75  # EX_TEMPFAIL; not 2, which Click uses for usage errors
_T = TypeVar("_T")


def _parse_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        console.print(
            Panel(
                f"[red]'{escape(raw)}' is not a valid entity id. Expected a UUID such "
                "as 123e4567-e89b-12d3-a456-426614174000.[/red]",
                title="Invalid entity id",
                border_style="red",
            )
        )
        raise typer.Exit(1) from exc


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run ``coro`` to completion; any error is shown and exits 1."""
    try:
        return asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 - surface any failure cleanly
        # escape(): an error text with [brackets] would otherwise be read as markup
        console.print(
            Panel(f"[red]{escape(str(exc))}[/red]", title="Error", border_style="red")
        )
        raise typer.Exit(1) from exc


def _breakdown(summary: ProcessSummary) -> str:
    return (
        "[bold]This run[/bold]\n"
        f"  scopes recomputed:          {summary.processed}\n"
        f"  records written:            {summary.records_written}\n"
        f"  errors:                     {summary.failed}\n"
        f"  skipped (database busy):    {summary.deferred}\n"
        "[bold]Left at the end[/bold]\n"
        f"  held by another worker:     {summary.locked_elsewhere}\n"
        f"  waiting to retry:           {summary.waiting_to_retry}\n"
        f"  failing ({FAILING_ATTEMPTS}+ attempts):      {summary.failing}\n"
        f"  not current (includes all of the above): {summary.remaining}"
    )


def _next_steps(summary: ProcessSummary) -> list[str]:
    """What to do about each cause of an incomplete run."""
    steps: list[str] = []
    if summary.failing or summary.waiting_to_retry:
        steps.append(
            "Errors are retried automatically with backoff. To retry now: "
            "`chronovista proximity retry-failed`, then re-run. Last errors: "
            "`chronovista proximity status`."
        )
    if summary.deferred:
        steps.append("The database was busy. Re-run the command; it resumes.")
    if summary.locked_elsewhere:
        steps.append(
            "Another worker (usually the API's) is processing some scopes. Wait and "
            "re-run, or check `chronovista proximity status`."
        )
    return steps or [
        "Re-run the command; it resumes. "
        "`chronovista proximity status` shows what is not current."
    ]


def _finish(summary: ProcessSummary, *, command: str) -> None:
    """Print the final breakdown; exit 0 if all current, 75 if work remains."""
    if summary.complete:
        body = _breakdown(summary)
        if not (summary.processed or summary.remaining):
            body += "\n\nNothing was stale: proximity is current."
        console.print(Panel(body, title=f"{command} complete", border_style="green"))
        return
    hints = "\n".join(f"- {step}" for step in _next_steps(summary))
    console.print(
        Panel(
            _breakdown(summary)
            + f"\n\n[yellow]{summary.remaining} scope(s) are not current.[/yellow]\n"
            + hints,
            title=f"{command} stopped: work remains",
            border_style="yellow",
        )
    )
    raise typer.Exit(EXIT_INCOMPLETE)


def _progress(step: ProcessSummary) -> None:
    console.print(
        f"  recomputed {step.processed}, errors {step.failed}, "
        f"skipped {step.deferred}; {step.remaining} not current"
    )


@proximity_app.command("rebuild")
def rebuild(
    video_id: list[str] = typer.Option(
        [],
        "--video-id",
        help="Only this video's scopes (repeatable). Omit for every scope.",
    ),
    entity_id: list[str] = typer.Option(
        [],
        "--entity-id",
        help="Only scopes where this entity is mentioned or already has proximity "
        "records (UUID, repeatable).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Recompute every scope from scratch, even current ones, and clear "
        "failure history. Slow; use after the proximity rules change.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview only: count the records the selected scopes would get, then "
        "discard them. With no --video-id/--entity-id it samples just 20 scopes, so "
        "it is not a corpus-wide check.",
    ),
) -> None:
    """Compute proximity for every scope that is not current (or only the requested).

    Resumable: scopes that are already current are skipped, so running it again
    after an interruption continues where it stopped. Only one rebuild runs at a time.
    Exits 0 when every scope is current, 75 if work remains, 1 on error.
    """
    entity_uuids = [_parse_uuid(raw) for raw in entity_id]
    if dry_run and force:
        console.print(
            Panel(
                "[red]--dry-run writes nothing, so --force (recompute everything) "
                "has no effect with it. Use one or the other.[/red]",
                title="Conflicting options",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if dry_run:
        report = _run(
            dry_run_proximity(
                video_ids=video_id or None, entity_ids=entity_uuids or None
            )
        )
        table = Table(
            title=(
                "DRY RUN (sample): records these scopes would get"
                if report.sampled
                else "DRY RUN: records these scopes would get"
            )
        )
        table.add_column("video")
        table.add_column("language")
        table.add_column("records", justify="right")
        for scope in report.scopes:
            table.add_row(scope.video_id, scope.language_code, str(scope.records))
        console.print(table)
        if report.sampled:
            coverage = (
                f"A sample of {len(report.scopes)} scope(s). These counts cover only "
                "the scopes listed; this is not a validation of the whole corpus."
            )
        elif report.scopes:
            coverage = f"{len(report.scopes)} requested scope(s)."
        else:
            coverage = "No matching scopes (check the video or entity id)."
        console.print(
            Panel(
                f"{coverage}\nNothing was written: no records, no scope state, no run. "
                "To apply, run without --dry-run.",
                title="DRY RUN",
                border_style="yellow",
            )
        )
        return

    console.print("Rebuilding proximity…")
    outcome = _run(
        rebuild_proximity(
            force=force,
            video_ids=video_id or None,
            entity_ids=entity_uuids or None,
            progress=_progress,
        )
    )
    if outcome.status == "locked" or outcome.summary is None:
        console.print(
            Panel(
                "[red]Another rebuild is running (it holds the rebuild lock). Wait for "
                "it to finish; `chronovista proximity status` shows its database "
                "session. The lock clears by itself when that session ends.[/red]",
                title="Rebuild refused",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    _finish(outcome.summary, command="Rebuild")


@proximity_app.command("drain")
def drain(
    limit: int = typer.Option(
        10_000,
        "--limit",
        min=1,
        help="Stop after this many scopes; re-run to continue.",
    ),
) -> None:
    """Recompute stale scopes now, as the API's background worker would.

    Use it when the API is not running. Unlike rebuild, it does not take the rebuild
    lock. Exits 0 when every scope is current, 75 if work remains, 1 on error.
    """
    summary = _run(drain_stale_scopes(limit=limit))
    _finish(summary, command="Drain")


@proximity_app.command("retry-failed")
def retry_failed_command(
    video_id: list[str] = typer.Option(
        [], "--video-id", help="Only this video's scopes (repeatable)."
    ),
) -> None:
    """Clear failure state (attempts, backoff, last error) so failing scopes are
    retried on the next drain or worker pass. Recomputes nothing itself."""
    reset = _run(retry_failed(video_ids=video_id or None))
    console.print(
        Panel(
            f"scopes reset: {reset}\nThe API's worker retries them on its next pass; "
            "to retry now, run `chronovista proximity drain`.",
            title="Failure state cleared",
            border_style="green",
        )
    )


@proximity_app.command("status")
def status() -> None:
    """Show how many scopes are current, stale or never computed, which are
    failing and why, and whether a rebuild is running.

    Current: computed from the latest transcript and mentions. Stale: they changed
    since. Not computed: never computed yet.
    """
    report = _run(proximity_status())
    oldest = (
        report.oldest_not_current_at.isoformat(timespec="seconds")
        if report.oldest_not_current_at
        else "none"
    )
    lock = (
        "held by a running rebuild (database session pid "
        f"{report.rebuild_lock_holder_pid})"
        if report.rebuild_lock_holder_pid is not None
        else "free"
    )
    if report.failing_total:
        hint = "Some scopes keep failing (see below); `proximity retry-failed` retries."
    elif report.stale or report.not_computed:
        hint = "Not all current: start the API, or run `chronovista proximity drain`."
    else:
        hint = "All current."
    console.print(
        Panel(
            f"rules version:         {report.rule_version} "
            "(after a change: rebuild --force)\n"
            f"current:               {report.current}\n"
            f"stale:                 {report.stale}\n"
            f"not computed:          {report.not_computed}\n"
            f"failing:               {report.failing_total}\n"
            f"oldest not current:    {oldest}\n"
            f"rebuild lock:          {lock}\n\n{hint}",
            title="Proximity status",
            border_style="blue",
        )
    )
    if report.failing:
        table = Table(title="Failing scopes (still retried with backoff)")
        table.add_column("video")
        table.add_column("language")
        table.add_column("attempts", justify="right")
        table.add_column("last error")
        for scope in report.failing:
            table.add_row(
                scope.video_id,
                scope.language_code,
                str(scope.attempts),
                scope.last_error or "",
            )
        console.print(table)
