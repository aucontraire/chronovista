"""Show transcript proximity for a pair, or an entity's closest partners (read-only).

A reviewer's view of the Feature 117 measurement before the evidence panel and graph
slices surface it: where two entities are mentioned close together in transcripts,
with the passages themselves, so a person can read them and decide what they mean.
Proximity is evidence, not a relationship.

    # a pair: its summary, then the passages (closest first, one block per video)
    python scripts/graph/proximity_pair.py "Entity A" "Entity B" --window 30

    # an entity's partners, most videos within the window first
    python scripts/graph/proximity_pair.py "Entity A" --partners --window 30

Entities are given by name (canonical name, else an alias; case-insensitive) or by
UUID. Every session is READ ONLY. Targets PROD via db_target (refuses a dev database
unless --allow-dev). The numbers come from the same repository reads the evidence
panel and graph will use, so this shows what they will show.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_HERE))  # db_target is vendored beside this script

import db_target  # noqa: E402  (prod-target guard)
from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402
from sqlalchemy import func, or_, select, text, tuple_  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from chronovista.config.database import db_manager  # noqa: E402
from chronovista.db.models import EntityAlias as EntityAliasDB  # noqa: E402
from chronovista.db.models import NamedEntity as NamedEntityDB  # noqa: E402
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB  # noqa: E402
from chronovista.db.models import Video as VideoDB  # noqa: E402
from chronovista.models.entity_pair_proximity import (  # noqa: E402
    PairProximitySummary,
)
from chronovista.repositories.entity_pair_proximity_repository import (  # noqa: E402
    EntityPairProximityRepository,
)
from chronovista.services.proximity_service import (  # noqa: E402
    MEASUREMENT_RULE_VERSION,
)

console = Console()
_repo = EntityPairProximityRepository()
_WINDOWS = (15, 30, 60, 120)


@asynccontextmanager
async def read_only() -> AsyncIterator[AsyncSession]:
    """A session that cannot write: the transaction is READ ONLY from its start."""
    async with db_manager.session() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        yield session


async def resolve(session: AsyncSession, given: str) -> tuple[uuid.UUID, str]:
    """An entity by UUID, exact canonical name, or alias (case-insensitive).

    Exits with a list of candidates when a name is ambiguous, rather than guess.
    """
    try:
        entity_id = uuid.UUID(given)
    except ValueError:
        entity_id = None
    if entity_id is not None:
        name = (
            await session.execute(
                select(NamedEntityDB.canonical_name).where(
                    NamedEntityDB.id == entity_id
                )
            )
        ).scalar_one_or_none()
        if name is None:
            raise SystemExit(f"no entity with id {given}")
        return entity_id, name

    folded = given.strip().lower()
    for stmt in (
        select(
            NamedEntityDB.id, NamedEntityDB.canonical_name, NamedEntityDB.entity_type
        ).where(func.lower(NamedEntityDB.canonical_name) == folded),
        select(
            NamedEntityDB.id, NamedEntityDB.canonical_name, NamedEntityDB.entity_type
        )
        .join(EntityAliasDB, EntityAliasDB.entity_id == NamedEntityDB.id)
        .where(func.lower(EntityAliasDB.alias_name) == folded)
        .distinct(),
    ):
        rows = (await session.execute(stmt)).all()
        if len(rows) == 1:
            return rows[0][0], rows[0][1]
        if len(rows) > 1:
            console.print(
                f"[yellow]'{given}' matches {len(rows)} entities; pass a UUID:[/yellow]"
            )
            for row in rows:
                console.print(f"  {row[0]}  {row[1]}  ({row[2]})")
            raise SystemExit(2)
    raise SystemExit(f"no entity named '{given}' (canonical name or alias)")


def _fmt_time(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def _settled(summary: PairProximitySummary) -> str:
    return (
        "[green]settled[/green]"
        if summary.complete
        else "[yellow]still updating (some scopes are not current)[/yellow]"
    )


async def show_pair(a: str, b: str, *, window: int, limit: int) -> None:
    async with read_only() as session:
        a_id, a_name = await resolve(session, a)
        b_id, b_name = await resolve(session, b)
        if a_id == b_id:
            raise SystemExit("those are the same entity")
        lo, hi = sorted((a_id, b_id))
        (summary,) = await _repo.pair_summaries(
            session, pairs=[(lo, hi)], rule_version=MEASUREMENT_RULE_VERSION
        )
        records = await _repo.records_for_pair(session, lo, hi, window_s=window)

        console.rule(f"{a_name}  ×  {b_name}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("within")
        table.add_column("videos", justify="right")
        table.add_column("segment pairs (density)", justify="right")
        for w in _WINDOWS:
            table.add_row(
                f"{w} s",
                str(getattr(summary, f"videos_within_{w}")),
                str(getattr(summary, f"segment_pairs_within_{w}")),
            )
        console.print(table)
        closest = (
            f"{summary.min_gap_seconds:.1f} s"
            if summary.min_gap_seconds is not None
            else "none"
        )
        console.print(f"closest: {closest}   status: {_settled(summary)}")
        if not records:
            console.print(f"\nNo co-mention within {window} s.")
            return

        # one block per video, closest first (records arrive ordered by gap)
        by_video: dict[str, list[object]] = {}
        for record in records:
            by_video.setdefault(record.video_id, []).append(record)
        shown = list(by_video)[:limit]
        segment_ids = {
            seg
            for vid in shown
            for r in by_video[vid]
            for seg in (r.segment_a_id, r.segment_b_id)  # type: ignore[attr-defined]
        }
        segments = {
            row.id: row
            for row in (
                await session.execute(
                    select(TranscriptSegmentDB).where(
                        TranscriptSegmentDB.id.in_(segment_ids)
                    )
                )
            ).scalars()
        }
        # A name can be split across two segments ("... author Norman" | "Surname ...");
        # a record anchors at the segment where the mention STARTS, so the segment
        # right after each passage is shown too, dimmed, as context.
        closest_segs = [
            segments[by_video[vid][0].segment_a_id] for vid in shown  # type: ignore[attr-defined]
        ] + [
            segments[by_video[vid][0].segment_b_id] for vid in shown  # type: ignore[attr-defined]
        ]
        following = {
            (row.video_id, row.language_code, row.sequence_number): row
            for row in (
                await session.execute(
                    select(TranscriptSegmentDB).where(
                        tuple_(
                            TranscriptSegmentDB.video_id,
                            TranscriptSegmentDB.language_code,
                            TranscriptSegmentDB.sequence_number,
                        ).in_(
                            [
                                (
                                    seg.video_id,
                                    seg.language_code,
                                    seg.sequence_number + 1,
                                )
                                for seg in closest_segs
                            ]
                        )
                    )
                )
            ).scalars()
        }
        titles = dict(
            (
                await session.execute(
                    select(VideoDB.video_id, VideoDB.title).where(
                        VideoDB.video_id.in_(shown)
                    )
                )
            )
            .tuples()
            .all()  # rows, not a mapping: Result has .keys()
        )
        console.print(
            f"\n{len(by_video)} video(s) within {window} s; showing the closest "
            f"{len(shown)}. Each block: the closest moment, its passages, and (dimmed) "
            "the segment after each.\n"
        )
        for vid in shown:
            first = by_video[vid][0]
            seg_a = segments[first.segment_a_id]  # type: ignore[attr-defined]
            seg_b = segments[first.segment_b_id]  # type: ignore[attr-defined]
            start = min(seg_a.start_time, seg_b.start_time)
            console.print(
                f"[bold]{titles.get(vid, vid)}[/bold]  [dim]({vid}, "
                f"{first.language_code}, {len(by_video[vid])} co-mention(s); "  # type: ignore[attr-defined]
                f"closest {first.gap_seconds:.1f} s)[/dim]"  # type: ignore[attr-defined]
            )
            console.print(f"  https://youtu.be/{vid}?t={max(int(start) - 5, 0)}")
            passage_ids = {seg_a.id, seg_b.id}
            lines = {seg.id: seg for seg in (seg_a, seg_b)}
            for seg in (seg_a, seg_b):
                nxt = following.get(
                    (seg.video_id, seg.language_code, seg.sequence_number + 1)
                )
                if nxt is not None:
                    lines.setdefault(nxt.id, nxt)
            for seg in sorted(lines.values(), key=lambda s: s.start_time):
                words = seg.corrected_text if seg.has_correction else seg.text
                if seg.id in passage_ids:
                    console.print(
                        f"  [cyan]{_fmt_time(seg.start_time)}[/cyan]  {words}"
                    )
                else:
                    console.print(f"  [dim]{_fmt_time(seg.start_time)}  {words}[/dim]")
            if len(passage_ids) == 1:
                console.print("  [dim](both mentioned in the first segment)[/dim]")
            console.print()


async def show_partners(entity: str, *, window: int, limit: int) -> None:
    async with read_only() as session:
        entity_id, name = await resolve(session, entity)
        summaries = await _repo.pair_summaries(
            session, entity_id=entity_id, rule_version=MEASUREMENT_RULE_VERSION
        )
        within = [s for s in summaries if getattr(s, f"videos_within_{window}") > 0]
        within.sort(
            key=lambda s: (
                -getattr(s, f"videos_within_{window}"),
                s.min_gap_seconds if s.min_gap_seconds is not None else 1e9,
            )
        )
        top = within[:limit]
        partner_ids = [
            s.entity_b_id if s.entity_a_id == entity_id else s.entity_a_id for s in top
        ]
        names = dict(
            (
                await session.execute(
                    select(NamedEntityDB.id, NamedEntityDB.canonical_name).where(
                        or_(NamedEntityDB.id.in_(partner_ids))
                    )
                )
            )
            .tuples()
            .all()  # rows, not a mapping: Result has .keys()
        )

        console.rule(f"closest partners of {name}  (within {window} s)")
        table = Table(show_header=True, header_style="bold")
        table.add_column("partner")
        table.add_column(f"videos ≤{window}s", justify="right")
        table.add_column(f"segment pairs ≤{window}s", justify="right")
        table.add_column("closest", justify="right")
        table.add_column("settled")
        for summary, partner in zip(top, partner_ids, strict=True):
            table.add_row(
                names.get(partner, str(partner)),
                str(getattr(summary, f"videos_within_{window}")),
                str(getattr(summary, f"segment_pairs_within_{window}")),
                f"{summary.min_gap_seconds:.1f} s",
                "yes" if summary.complete else "[yellow]no[/yellow]",
            )
        console.print(table)
        console.print(
            f"{len(within)} partner(s) within {window} s; {len(summaries)} within the "
            "120 s outer window. Open one with: "
            f'proximity_pair.py "{name}" "<partner>"'
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("entity", help="entity name, alias, or UUID")
    ap.add_argument("other", nargs="?", help="second entity (pair mode)")
    ap.add_argument("--partners", action="store_true", help="list the closest partners")
    ap.add_argument("--window", type=int, choices=_WINDOWS, default=30)
    ap.add_argument("--limit", type=int, default=10, help="videos (pair) or partners")
    db_target.add_argument(ap)
    args = ap.parse_args()
    if args.partners == (args.other is not None):
        ap.error("give two entities, or one entity with --partners")
    db_target.use(args.database_url, allow_dev=args.allow_dev)

    if args.partners:
        asyncio.run(show_partners(args.entity, window=args.window, limit=args.limit))
    else:
        asyncio.run(
            show_pair(args.entity, args.other, window=args.window, limit=args.limit)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
