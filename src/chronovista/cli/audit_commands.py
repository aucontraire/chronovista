"""``chronovista audit-invariants``: check that the library's data obeys its rules.

Read-only. Each check verifies one entry in ``docs/architecture/invariants.md``. Save a
run before a change to data and compare after it: the comparison fails on anything
new, even when a total fell, which is the before-and-after gate register entry D4 asks
for.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from chronovista.config.database import db_manager
from chronovista.config.settings import settings
from chronovista.services.invariant_audit_service import (
    REGISTRY,
    AuditRun,
    CheckComparison,
    InvariantCheck,
    compare,
    exit_code,
    run_checks,
    select_checks,
)

console = Console()


def _inside_repo_and_not_ignored(path: Path) -> bool:
    """Whether ``path`` lies in a git work tree and git does not ignore it.

    An error from ``git check-ignore`` counts as "not ignored", so the guard fails
    safe. Without git, nothing is a repository.
    """
    folder = path.resolve().parent
    try:
        inside = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0:
            return False
        ignored = subprocess.run(
            ["git", "-C", str(folder), "check-ignore", "-q", str(path.resolve())],
            check=False,
        )
    except FileNotFoundError:
        return False
    return ignored.returncode != 0


def _print_run(run: AuditRun) -> None:
    console.print(
        f"[bold]Invariant audit[/bold] — {len(run.results)} checks, "
        f"{run.started_at:%Y-%m-%d %H:%M} UTC\n"
    )
    for result in run.results:
        if result.outcome == "holds":
            label, detail = "[green]holds   [/green]", ""
        elif result.outcome == "violated":
            label, detail = "[red]VIOLATED[/red]", f"{result.violation_count}"
        else:
            label, detail = "[yellow]ERROR   [/yellow]", result.error or ""
        console.print(
            f"  {label}  {result.check_id:<28} {detail:<12} ({result.seconds:.1f}s)"
        )
    counts = {
        o: sum(r.outcome == o for r in run.results)
        for o in ("holds", "violated", "error")
    }
    console.print(
        f"\n{counts['holds']} hold · {counts['violated']} violated · {counts['error']} error"
    )


def _print_comparison(
    baseline: AuditRun, comparisons: list[CheckComparison], show_keys: bool
) -> None:
    console.print(
        f"\nCompared with the baseline of {baseline.started_at:%Y-%m-%d %H:%M} UTC\n"
    )
    if show_keys:
        console.print(
            "[yellow]--show-keys: this output contains library identifiers. "
            "Do not paste it anywhere public.[/yellow]"
        )
    for c in comparisons:
        if c.status == "not_compared":
            console.print(f"  {c.check_id:<28} not compared ({c.reason})")
            continue
        line = f"  {c.check_id:<28} resolved {c.resolved:<5} new {c.new}"
        if c.sample_new:
            line += "   e.g. " + ", ".join(c.sample_new)
        elif c.hidden_keys:
            line += "   (keys hidden: library identifiers; use --show-keys)"
        console.print(line)
    new = sum(c.new for c in comparisons)
    if new:
        checks = sum(1 for c in comparisons if c.new)
        console.print(f"\n[red]FAIL: {new} new violations in {checks} checks[/red]")


async def _audit(
    checks: list[InvariantCheck],
    save: Path | None,
    baseline: AuditRun | None,
    sample: int,
    show_keys: bool,
) -> int:
    async with db_manager.session(read_only=True) as session:
        run = await run_checks(
            session,
            checks,
            database_url=settings.effective_database_url,
        )
    _print_run(run)
    comparisons = None
    if baseline is not None:
        if baseline.database_hash != run.database_hash:
            console.print(
                "[yellow]The baseline came from a different database; comparing "
                "anyway.[/yellow]"
            )
        comparisons = compare(baseline, run, sample=sample, show_library_keys=show_keys)
        _print_comparison(baseline, comparisons, show_keys)
    if save is not None:
        try:
            # Readable by the owner only: the file holds library identifiers.
            descriptor = os.open(save, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as out:
                out.write(run.model_dump_json())
        except OSError:
            console.print(f"[red]Could not write {save}.[/red]")
            return 2
        console.print(f"\nSaved this run to {save}.")
    return exit_code(run, comparisons)


def audit_invariants(
    check: list[str] | None = typer.Option(
        None,
        "--check",
        help="Run only this check, by check ID or register entry (repeatable).",
    ),
    list_checks: bool = typer.Option(
        False, "--list", help="List the checks and the rules they verify; run nothing."
    ),
    save: Path | None = typer.Option(
        None, "--save", help="Save this run, with the violating keys, as a baseline."
    ),
    force: bool = typer.Option(
        False, "--force", help="Allow --save to write inside the repository."
    ),
    compare_with: Path | None = typer.Option(
        None, "--compare", help="Compare with a saved baseline; fail on anything new."
    ),
    sample: int = typer.Option(
        5, "--sample", min=0, help="New keys to show per check when comparing."
    ),
    show_keys: bool = typer.Option(
        False,
        "--show-keys",
        help="Also show keys built from library identifiers (video IDs).",
    ),
) -> None:
    """Check that the library's data obeys the invariant register's rules.

    Reads only: the database itself refuses writes for the whole run, and every
    check sees one snapshot. Exits 0 when every check holds (or, with --compare,
    nothing is new), 1 on a violation, and 75 when a check could not run.

    Saved runs hold library keys: keep them out of the repository (backups/ is
    ignored by git).
    """
    try:
        checks = select_checks(REGISTRY, check)
    except ValueError as unknown:
        valid = ", ".join(c.check_id for c in REGISTRY)
        raise typer.BadParameter(
            f"unknown check {unknown}. Valid: {valid}", param_hint="--check"
        ) from None
    if list_checks:
        for c in checks:
            console.print(f"{c.check_id:<28} {c.register_entry:<4} {c.rule}")
        return
    if save is not None and not save.resolve().parent.is_dir():
        console.print(f"[red]{save.parent} does not exist; create it first.[/red]")
        raise typer.Exit(2)
    if save is not None and not force and _inside_repo_and_not_ignored(save):
        console.print(
            f"[red]{save} is inside the repository and not ignored. Saved runs hold "
            "library keys; save under backups/, or pass --force.[/red]"
        )
        raise typer.Exit(2)
    baseline = None
    if compare_with is not None:
        try:
            baseline = AuditRun.model_validate_json(
                compare_with.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError):
            # Never print the parser's message: it can quote a key, and keys can be
            # library identifiers.
            console.print(
                f"[red]{compare_with} is not a readable audit baseline.[/red]"
            )
            raise typer.Exit(2) from None
    code = asyncio.run(_audit(checks, save, baseline, sample, show_keys))
    raise typer.Exit(code)
