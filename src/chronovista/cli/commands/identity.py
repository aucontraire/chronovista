"""
CLI commands for the canonical local-user identity (Feature 060).

``chronovista identity status``  — show the persisted identity and health.
``chronovista identity repair``  — collapse duplicate watch-history identities.
``chronovista identity reset``   — fold an offline identity into a real channel.
"""

from __future__ import annotations

import asyncio
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronovista.config.database import DatabaseManager
from chronovista.repositories.app_identity_repository import AppIdentityRepository
from chronovista.repositories.user_video_repository import UserVideoRepository
from chronovista.services.identity_service import IdentityError, IdentityService

console = Console()

identity_app = typer.Typer(
    name="identity",
    help="🪪 Canonical local-user identity: status, repair (dedup), reset",
    no_args_is_help=True,
)


@identity_app.command()
def status() -> None:
    """Show the persisted canonical identity and duplicate-identity health."""

    async def status_async() -> None:
        identity_repo = AppIdentityRepository()
        user_video_repo = UserVideoRepository()
        db_manager = DatabaseManager()

        async for session in db_manager.get_session(echo=False):
            identity = await identity_repo.get_identity(session)
            distinct = await user_video_repo.list_distinct_user_ids(session)

            table = Table(show_header=True, header_style="bold")
            table.add_column("Property")
            table.add_column("Value")
            if identity is None:
                table.add_row("Canonical identity", "[yellow]not established[/yellow]")
            else:
                table.add_row("Canonical identity", identity.user_id)
                table.add_row("Source", identity.source)
            table.add_row(
                "Distinct user_ids in user_videos",
                str(len(distinct)),
            )
            console.print(table)

            if len(distinct) > 1:
                console.print(
                    Panel(
                        f"[bold red]Multiple identities detected[/bold red] in "
                        f"user_videos: {distinct}. Run "
                        f"[bold]chronovista identity repair --dry-run[/bold] to "
                        f"preview a fix.",
                        border_style="red",
                    )
                )

    asyncio.run(status_async())


@identity_app.command()
def repair(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the merge without writing to the database.",
    ),
) -> None:
    """Collapse duplicate watch-history identities into the canonical one.

    Lossless merge-then-delete in a single transaction, with before/after
    integrity checks and a recoverable pre-image. Idempotent and safe to re-run.
    """

    async def repair_async() -> None:
        service = IdentityService()
        db_manager = DatabaseManager()
        # Never `return`/`sys.exit()` from inside the `async for` below: that
        # abandons the session generator mid-yield, so its cleanup (commit /
        # close / engine dispose) is forced to run during loop teardown and
        # prints a CancelledError traceback after an otherwise-successful run.
        # Record the outcome instead and act once the loop has finished.
        failure: IdentityError | None = None

        try:
            async for session in db_manager.get_session(echo=False):
                try:
                    report = await service.repair(session, dry_run=dry_run)
                except IdentityError as exc:
                    failure = exc
                    continue

                header = (
                    "[bold]Identity repair (dry-run)[/bold] — no changes written"
                    if dry_run
                    else "[bold]Identity repair[/bold] — applied"
                )
                console.print(
                    Panel(header, border_style="yellow" if dry_run else "green")
                )

                if not report.placeholder_user_ids:
                    console.print(
                        "[dim]Only one identity present — nothing to merge.[/dim]"
                    )
                    continue

                table = Table(show_header=True, header_style="bold")
                table.add_column("Field")
                table.add_column("Value", justify="right")
                table.add_row("Survivor identity", report.canonical_user_id)
                table.add_row(
                    "Merged (placeholders)", ", ".join(report.placeholder_user_ids)
                )
                table.add_row("Rows merged (overlap)", str(report.user_videos.merged))
                table.add_row("Rows deleted (overlap)", str(report.user_videos.deleted))
                table.add_row("Rows re-keyed", str(report.user_videos.rekeyed))
                table.add_row(
                    "Distinct watched videos",
                    f"{report.invariants_before.distinct_watched_videos} → "
                    f"{report.invariants_after.distinct_watched_videos}",
                )
                table.add_row(
                    "Liked count",
                    f"{report.invariants_before.liked_count} → "
                    f"{report.invariants_after.liked_count}",
                )
                if report.pre_image_path:
                    table.add_row("Pre-image", report.pre_image_path)
                console.print(table)

                if dry_run:
                    console.print("[dim]Re-run without --dry-run to apply.[/dim]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled by user[/yellow]")
            sys.exit(1)

        if failure is not None:
            console.print(Panel(f"[red]{failure}[/red]", border_style="red"))
            sys.exit(1)

    asyncio.run(repair_async())


@identity_app.command()
def reset(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the reset without writing to the database.",
    ),
) -> None:
    """Fold an offline local identity into your now-authenticated channel.

    Use after authenticating if an earlier offline load established a local
    identity. Re-keys your data onto the real channel via the same lossless
    merge as ``repair``.
    """

    async def reset_async() -> None:
        from chronovista.container import container

        service = IdentityService()
        db_manager = DatabaseManager()

        try:
            my_channel = await container.youtube_service.get_my_channel()
        except Exception as exc:  # noqa: BLE001 - surface any resolution failure
            console.print(
                Panel(
                    f"[red]Could not resolve your channel: {exc}[/red]",
                    border_style="red",
                )
            )
            sys.exit(1)

        if not my_channel:
            console.print(
                Panel(
                    "[red]No YouTube channel found for the authenticated "
                    "account — cannot reset to a channel identity.[/red]",
                    border_style="red",
                )
            )
            sys.exit(1)

        # See the note in `repair_async`: never exit the loop body early, or the
        # session generator is abandoned mid-yield and its teardown noise lands
        # on top of the command's output.
        failure: IdentityError | None = None

        async for session in db_manager.get_session(echo=False):
            try:
                report = await service.reset_identity(
                    session,
                    authenticated_channel_id=my_channel.id,
                    dry_run=dry_run,
                )
            except IdentityError as exc:
                failure = exc
                continue

            header = (
                "[bold]Identity reset (dry-run)[/bold] — no changes written"
                if dry_run
                else "[bold]Identity reset[/bold] — applied"
            )
            console.print(Panel(header, border_style="yellow" if dry_run else "green"))
            console.print(
                f"Identity is now [bold]{report.canonical_user_id}[/bold] "
                f"(re-keyed {report.user_videos.rekeyed} rows)."
            )

        if failure is not None:
            console.print(Panel(f"[red]{failure}[/red]", border_style="red"))
            sys.exit(1)

    asyncio.run(reset_async())
