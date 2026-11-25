"""The world and helpers the transcript-mention tests share (#426, Feature 117).

One video, two entities (placeholder names), one close pair of segments per language,
plus the helpers every mention test needs to drive the REAL entry points (batch
correction, single correction, scan, repair, the Typer command) and to read what they
left behind. Everything is synthetic: nonsense names and generated video ids.

These are public names on purpose: a test module must never import another test
module's private helpers.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Coroutine, Sequence
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner
from uuid_utils import uuid7

from chronovista.cli import entity_commands
from chronovista.cli.main import app as cli_app
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityAsrError as EntityAsrErrorDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.entity_pair_proximity import ScopeFilter
from chronovista.models.enums import CorrectionType
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.repositories.transcript_correction_repository import (
    TranscriptCorrectionRepository,
)
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.batch_correction_service import BatchCorrectionService
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from chronovista.services.proximity_service import (
    MEASUREMENT_RULE_VERSION,
    process_stale_scopes,
)
from chronovista.services.tag_normalization import TagNormalizationService
from chronovista.services.transcript_correction_service import (
    TranscriptCorrectionService,
)
from chronovista.services.transcript_text_index import SegmentInput, TranscriptTextIndex
from tests.factories.proximity_seed import (
    route_proximity_service_to,
    seed_mention,
    seed_segment,
    seed_video,
)

A_NAME = "Zeta Quux"
B_NAME = "Yodel Vance"
GARBLE = "Zeta Quuks"
SURNAME = A_NAME.split(" ")[1]
GARBLED_SURNAME = GARBLE.split(" ")[1]

_normalizer = TagNormalizationService()


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------


class World(BaseModel):
    """One video, two entities, one close pair per language."""

    video_id: str
    languages: tuple[str, ...]
    a: uuid.UUID
    b: uuid.UUID
    seg_a: dict[str, int]
    seg_b: dict[str, int]


def new_video_id() -> str:
    """A generated 11-character id: a valid ``VideoId``."""
    return f"pp{uuid.uuid4().hex[:9]}"


def new_batch_id() -> uuid.UUID:
    return uuid.UUID(bytes=uuid7().bytes)


async def make_entity(
    session: AsyncSession,
    name: str,
    *,
    entity_type: str = "person",
    normalized: str | None = None,
    with_alias: bool = True,
) -> uuid.UUID:
    """Persist an active entity (plus its self-alias, which scanning needs)."""
    norm = normalized or _normalizer.normalize(name) or name.lower()
    entity = NamedEntityDB(
        canonical_name=name,
        canonical_name_normalized=norm,
        entity_type=entity_type,
        status="active",
        discovery_method="manual",
        confidence=1.0,
        mention_count=0,
        video_count=0,
    )
    session.add(entity)
    await session.flush()
    if with_alias:
        await add_alias(session, entity.id, name)
    return uuid.UUID(str(entity.id))


async def add_alias(
    session: AsyncSession, entity_id: uuid.UUID, alias_name: str
) -> uuid.UUID:
    alias = EntityAliasDB(
        entity_id=entity_id,
        alias_name=alias_name,
        alias_name_normalized=_normalizer.normalize(alias_name) or alias_name.lower(),
        alias_type="name_variant",
        occurrence_count=0,
    )
    session.add(alias)
    await session.flush()
    return uuid.UUID(str(alias.id))


async def add_asr_form(session: AsyncSession, entity_id: uuid.UUID, form: str) -> None:
    """Register ``form`` as a known mishearing of the entity (an ASR error form)."""
    session.add(
        EntityAsrErrorDB(
            entity_id=entity_id,
            alias_name=form,
            alias_name_normalized=_normalizer.normalize(form) or form.lower(),
        )
    )
    await session.flush()


async def seed_world(
    session: AsyncSession,
    *,
    languages: Sequence[str] = ("en",),
    a_mention_text: str | None = None,
    a_mentioned: bool = True,
    a_detection: str = "rule_match",
    a_alias: bool = True,
    a_name: str = A_NAME,
    a_segment_text: str | None = None,
    b_segment_text: str | None = None,
    a_match_start: int | None = None,
    a_match_end: int | None = None,
) -> World:
    """Co-mention entities A and B 4 seconds apart in every language of one video.

    ``a_mention_text`` defaults to A's canonical name (so the mention qualifies); pass
    another string to seed a mention that does NOT qualify until a producer changes
    the entity's visible names. ``a_mentioned=False`` seeds only B (for scan tests).
    ``a_match_start`` / ``a_match_end`` position A's mention in its segment's text.
    """
    video_id = new_video_id()
    a = await make_entity(session, a_name, with_alias=a_alias)
    b = await make_entity(session, B_NAME)
    await seed_video(session, video_id, languages)
    seg_a: dict[str, int] = {}
    seg_b: dict[str, int] = {}
    for language in languages:
        seg_a[language] = await seed_segment(session, video_id, language, 10.0, 0)
        seg_b[language] = await seed_segment(session, video_id, language, 14.0, 1)
        for segment_id, text in (
            (seg_a[language], a_segment_text),
            (seg_b[language], b_segment_text),
        ):
            if text is not None:
                await set_text(session, segment_id, text)
        if a_mentioned:
            await seed_mention(
                session,
                entity_id=a,
                video_id=video_id,
                language_code=language,
                segment_id=seg_a[language],
                mention_text=a_mention_text,
                detection_method=a_detection,
                match_start=a_match_start,
                match_end=a_match_end,
            )
        await seed_mention(
            session,
            entity_id=b,
            video_id=video_id,
            language_code=language,
            segment_id=seg_b[language],
        )
    return World(
        video_id=video_id,
        languages=tuple(languages),
        a=a,
        b=b,
        seg_a=seg_a,
        seg_b=seg_b,
    )


async def seed_segments(
    session: AsyncSession, a_text: str, b_text: str = f"then {B_NAME} replied"
) -> tuple[uuid.UUID, str, int, int]:
    """A world with no mention of A and the two segments' text set.

    Returns ``(entity_a, video_id, segment_a, segment_b)``.
    """
    world = await seed_world(
        session, a_mentioned=False, a_segment_text=a_text, b_segment_text=b_text
    )
    return world.a, world.video_id, world.seg_a["en"], world.seg_b["en"]


async def seed_three_segment_world(
    session: AsyncSession, entity_name: str = "Zeta Quux Nine"
) -> tuple[uuid.UUID, str, int, int, int]:
    """A name spread over three segments: ``Zeta`` | ``Quux`` | ``Nine is here``.

    Creates a new entity with that name (not the world's A). Returns
    ``(entity, video_id, first, middle, last)``.
    """
    entity = await make_entity(session, entity_name)
    _a, video, first, middle = await seed_segments(session, "we saw Zeta", "Quux")
    last = await seed_segment(session, video, "en", 18.0, 2)
    await set_text(session, last, "Nine is here")
    return entity, video, first, middle, last


async def set_text(session: AsyncSession, segment_id: int, text: str) -> None:
    await session.execute(
        update(TranscriptSegmentDB)
        .where(TranscriptSegmentDB.id == segment_id)
        .values(text=text)
    )
    await session.flush()


async def mark_corrected(session: AsyncSession, segment_id: int, text: str) -> None:
    """Make ``text`` the segment's effective text, as an applied correction would."""
    await session.execute(
        update(TranscriptSegmentDB)
        .where(TranscriptSegmentDB.id == segment_id)
        .values(corrected_text=text, has_correction=True)
    )
    await session.flush()


async def place(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
    video_id: str,
    segment_id: int,
    start: int,
    mention_text: str,
    end: int | None = None,
    method: str = "rule_match",
    end_segment_id: int | None = None,
) -> None:
    """Seed one positioned English mention (``end`` defaults to the text's length).

    For a cross-segment mention ``end`` is an offset into the END segment.
    """
    await seed_mention(
        session,
        entity_id=entity_id,
        video_id=video_id,
        language_code="en",
        segment_id=segment_id,
        end_segment_id=end_segment_id,
        mention_text=mention_text,
        detection_method=method,
        match_start=start,
        match_end=end,
    )


# ---------------------------------------------------------------------------
# Proximity scope observation
# ---------------------------------------------------------------------------


async def scope_state(
    session: AsyncSession, video_id: str, language: str = "en"
) -> ProximityScopeStateDB:
    result = await session.execute(
        select(ProximityScopeStateDB)
        .where(
            ProximityScopeStateDB.video_id == video_id,
            ProximityScopeStateDB.language_code == language,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def is_current(state: ProximityScopeStateDB) -> bool:
    return (
        state.computed_revision == state.revision
        and state.computed_rule_version == MEASUREMENT_RULE_VERSION
    )


async def recompute(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """Process the video's stale scopes WITHOUT invalidating first."""
    route_proximity_service_to(monkeypatch, session)
    summary = await process_stale_scopes(
        limit=10_000, scope_filter=ScopeFilter(video_ids=(world.video_id,))
    )
    assert summary.remaining == 0, f"recompute left scopes unsettled: {summary}"


async def settle(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """Force-invalidate every language then recompute, so each scope is CURRENT."""
    await EntityPairProximityRepository().invalidate_proximity_scopes(
        session, video_id=world.video_id, reason="test"
    )
    await recompute(session, monkeypatch, world)
    for language in world.languages:
        assert is_current(await scope_state(session, world.video_id, language))


# ---------------------------------------------------------------------------
# Service plumbing
# ---------------------------------------------------------------------------


def session_factory(session: AsyncSession) -> Any:
    """A ``session_factory`` stand-in that always yields the test session."""

    class _CM:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *exc: object) -> bool:
            return False

    class _Factory:
        def __call__(self) -> _CM:
            return _CM()

    return _Factory()


def correction_service() -> TranscriptCorrectionService:
    return TranscriptCorrectionService(
        correction_repo=TranscriptCorrectionRepository(),
        segment_repo=TranscriptSegmentRepository(),
        transcript_repo=VideoTranscriptRepository(),
    )


def batch_service() -> BatchCorrectionService:
    correction_repo = TranscriptCorrectionRepository()
    segment_repo = TranscriptSegmentRepository()
    return BatchCorrectionService(
        correction_service=TranscriptCorrectionService(
            correction_repo=correction_repo,
            segment_repo=segment_repo,
            transcript_repo=VideoTranscriptRepository(),
        ),
        segment_repo=segment_repo,
        correction_repo=correction_repo,
    )


class FixedSessionDbManager:
    """Stand-in for ``db_manager`` yielding one fixed session (CLI plumbing)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def session(self, echo: bool | None = None) -> AsyncIterator[AsyncSession]:
        yield self._session


async def invoke_cli(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession, args: list[str]
) -> None:
    """Run a real ``chronovista entities ...`` command against the test session.

    The command is parsed by Typer exactly as in production. Its body is an inner
    ``async def _run`` handed to ``asyncio.run``; that call cannot nest inside the test
    loop, so it is captured and the real coroutine is awaited here instead.
    """
    captured: list[Coroutine[Any, Any, None]] = []

    def _capture(coro: Coroutine[Any, Any, None]) -> None:
        captured.append(coro)

    monkeypatch.setattr(
        entity_commands, "asyncio", SimpleNamespace(run=_capture, sleep=asyncio.sleep)
    )
    monkeypatch.setattr(entity_commands, "db_manager", FixedSessionDbManager(session))
    result = CliRunner().invoke(cli_app, ["entities", *args])
    assert result.exit_code == 0, f"CLI rejected its arguments: {result.output}"
    assert len(captured) == 1, "expected exactly one asyncio.run(_run()) call"
    await captured[0]


# ---------------------------------------------------------------------------
# Driving the entry points
# ---------------------------------------------------------------------------


async def scan(
    session: AsyncSession,
    video_id: str,
    entity_ids: list[uuid.UUID],
    *,
    full: bool,
) -> None:
    await EntityMentionScanService(session_factory=session_factory(session)).scan(
        video_ids=[video_id], entity_ids=entity_ids, full_rescan=full
    )


async def correct(
    session: AsyncSession,
    segment_id: int,
    pattern: str,
    replacement: str,
    entity_id: uuid.UUID | None = None,
    *,
    cross_segment: bool = False,
    batch_id: uuid.UUID | None = None,
) -> Any:
    """A batch correction of one segment; every row of it must apply."""
    result = await batch_service().apply_to_segments(
        session,
        pattern=pattern,
        replacement=replacement,
        segment_ids=[segment_id],
        correction_type=CorrectionType.PROPER_NOUN,
        auto_rebuild=False,
        entity_id=entity_id,
        cross_segment=cross_segment,
        batch_id=batch_id or new_batch_id(),
    )
    assert result.total_failed == 0, result
    return result


async def apply_text(
    session: AsyncSession, video_id: str, segment_id: int, text: str
) -> None:
    """Replace a segment's whole text through ``apply_correction``."""
    await correction_service().apply_correction(
        session,
        video_id=video_id,
        language_code="en",
        segment_id=segment_id,
        corrected_text=text,
        correction_type=CorrectionType.PROPER_NOUN,
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Reading what they left behind
# ---------------------------------------------------------------------------


async def effective_text(session: AsyncSession, segment_id: int) -> str:
    seg = (
        await session.execute(
            select(TranscriptSegmentDB)
            .where(TranscriptSegmentDB.id == segment_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if seg.has_correction and seg.corrected_text:
        return str(seg.corrected_text)
    return str(seg.text)


async def mentions(
    session: AsyncSession, entity_id: uuid.UUID, segment_id: int
) -> list[EntityMentionDB]:
    """The entity's mentions that START in ``segment_id``, in offset order."""
    return list(
        (
            await session.execute(
                select(EntityMentionDB)
                .where(
                    EntityMentionDB.entity_id == entity_id,
                    EntityMentionDB.segment_id == segment_id,
                )
                .order_by(EntityMentionDB.match_start)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def describe(text: str, rows: list[EntityMentionDB]) -> str:
    lines = [
        f"{m.detection_method}: text={m.mention_text!r} "
        f"offsets={m.match_start}-{m.match_end} "
        f"slice={text[m.match_start or 0 : m.match_end or 0]!r}"
        for m in rows
    ]
    return f"segment text={text!r}\n  " + "\n  ".join(lines)


async def transcript_segments(
    session: AsyncSession, video_id: str
) -> list[TranscriptSegmentDB]:
    return list(
        (
            await session.execute(
                select(TranscriptSegmentDB)
                .where(
                    TranscriptSegmentDB.video_id == video_id,
                    TranscriptSegmentDB.language_code == "en",
                )
                .order_by(TranscriptSegmentDB.sequence_number)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def text_index(session: AsyncSession, video_id: str) -> TranscriptTextIndex:
    return TranscriptTextIndex.from_segments(
        [
            SegmentInput(
                segment_id=s.id,
                text=s.text,
                corrected_text=s.corrected_text,
                has_correction=s.has_correction,
            )
            for s in await transcript_segments(session, video_id)
        ]
    )


async def positioned(session: AsyncSession, video_id: str) -> list[EntityMentionDB]:
    """Every positioned transcript mention of the video, in transcript order."""
    return list(
        (
            await session.execute(
                select(EntityMentionDB)
                .where(
                    EntityMentionDB.video_id == video_id,
                    EntityMentionDB.mention_source == "transcript",
                    EntityMentionDB.match_start.is_not(None),
                )
                .order_by(EntityMentionDB.segment_id, EntityMentionDB.match_start)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def count_of(session: AsyncSession, entity_id: uuid.UUID, video_id: str) -> int:
    return len(
        [m for m in await positioned(session, video_id) if m.entity_id == entity_id]
    )


async def snapshot(session: AsyncSession, video_id: str) -> list[tuple[Any, ...]]:
    """Every positioned mention's identity and offsets, sorted: equal snapshots mean
    nothing moved, appeared or vanished."""
    return sorted(
        (
            str(m.entity_id),
            m.segment_id,
            m.end_segment_id or -1,
            m.match_start,
            m.match_end,
            m.mention_text,
            m.detection_method,
        )
        for m in await positioned(session, video_id)
    )


def _row(index: TranscriptTextIndex, m: EntityMentionDB) -> str:
    loc = index.locate(
        segment_id=m.segment_id,
        end_segment_id=m.end_segment_id,
        match_start=m.match_start,
        match_end=m.match_end,
    )
    sl = index.text[loc[0] : loc[1]] if loc else None
    return (
        f"{m.detection_method}: ent={str(m.entity_id)[:8]} text={m.mention_text!r} "
        f"seg={m.segment_id}->{m.end_segment_id} "
        f"offsets={m.match_start}-{m.match_end} slice={sl!r}"
    )


async def mention_report(
    session: AsyncSession, video_id: str
) -> tuple[list[str], list[str], list[str], str]:
    """``(rows not reading as their text, same-entity overlaps, rows inside a larger
    word, description of every row)``."""
    index = await text_index(session, video_id)
    rows = await positioned(session, video_id)
    bad: list[str] = []
    boundary: list[str] = []
    located: list[tuple[uuid.UUID, int, int, EntityMentionDB]] = []
    for m in rows:
        loc = index.locate(
            segment_id=m.segment_id,
            end_segment_id=m.end_segment_id,
            match_start=m.match_start,
            match_end=m.match_end,
        )
        if loc is None:
            bad.append(_row(index, m))
            continue
        s, e = loc
        if index.text[s:e].casefold() != m.mention_text.casefold():
            bad.append(_row(index, m))
        else:
            before = index.text[s - 1] if s > 0 else " "
            after = index.text[e] if e < len(index.text) else " "
            if before.isalnum() or after.isalnum():
                boundary.append(_row(index, m))
        located.append((m.entity_id, s, e, m))
    overlaps: list[str] = []
    for i, (ea, sa, xa, ma) in enumerate(located):
        for eb, sb, xb, mb in located[i + 1 :]:
            if ea == eb and sa < xb and sb < xa:
                overlaps.append(f"{_row(index, ma)}  <>  {_row(index, mb)}")
    desc = f"text={index.text!r}\n  " + "\n  ".join(_row(index, m) for m in rows)
    return bad, overlaps, boundary, desc


async def assert_mentions_ok(
    session: AsyncSession, video_id: str, *, boundaries: bool = True
) -> str:
    """The invariants: every positioned mention reads as its text, no entity has two
    overlapping mentions, and (optionally) none sits inside a longer word."""
    bad, overlaps, boundary, desc = await mention_report(session, video_id)
    assert not bad, f"offsets do not read as mention_text:\n{desc}"
    assert not overlaps, f"same-entity mentions overlap:\n{desc}"
    if boundaries:
        assert not boundary, f"mention sits inside a larger word:\n{desc}"
    return desc
