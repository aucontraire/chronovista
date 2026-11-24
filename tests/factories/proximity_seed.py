"""Seeding helpers for Features 116/117 (transcript proximity) integration tests.

Everything is synthetic: entities come from ``NamedEntityDBFactory`` (sequence
names) and video ids are generated, so no library data appears in a fixture.

``rebuild_proximity`` opens its own session through the module-level
``db_manager``; :func:`route_proximity_service_to` points that at the test's
session so the service runs against the same (per-test, create_all'd) tables
the seed wrote to, instead of whatever DSN the process was configured with.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import UserLanguagePreference as UserLanguagePreferenceDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from chronovista.services.proximity_service import (
    MEASUREMENT_RULE_VERSION,
    OUTER_WINDOW_SECONDS,
)
from tests.factories.named_entity_orm_factory import create_named_entity_db


class _SessionScope:
    """Stand-in for ``db_manager`` that yields one fixed session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def session(self, echo: bool | None = None) -> AsyncIterator[AsyncSession]:
        yield self._session
        await self._session.flush()

    def get_engine(self) -> AsyncEngine:
        """The session's engine, for code that needs its own connection (locks)."""
        bind = self._session.bind
        assert isinstance(bind, AsyncEngine)
        return bind


class _EngineScope:
    """Stand-in for ``db_manager`` over a real engine: a NEW session per call that
    commits on success and rolls back on error (``db_manager.session`` semantics).

    Unlike :class:`_SessionScope`, concurrent callers get separate connections, so
    row locks and transactions behave as they do in production.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._factory = async_sessionmaker(engine, expire_on_commit=False)

    def get_engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self, echo: bool | None = None) -> AsyncIterator[AsyncSession]:
        async with self._factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise


def route_proximity_service_to_engine(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
) -> None:
    """Make ``proximity_service`` open real, separate sessions on ``engine``."""
    monkeypatch.setattr(
        "chronovista.services.proximity_service.db_manager", _EngineScope(engine)
    )


def route_proximity_service_to(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """Make ``proximity_service.rebuild_proximity`` use ``session``."""
    monkeypatch.setattr(
        "chronovista.services.proximity_service.db_manager", _SessionScope(session)
    )


async def seed_entity(session: AsyncSession, *, unique: bool = False) -> uuid.UUID:
    """Persist one factory-built entity with a sequence (placeholder) name.

    ``unique=True`` suffixes a random token so the row cannot collide with
    ``uq_named_entity_canonical`` against rows that outlive a test (committed
    through the API's own sessions on the shared integration DB).
    """
    entity: NamedEntityDB = create_named_entity_db()
    if unique:
        token = uuid.uuid4().hex
        entity.canonical_name = f"{entity.canonical_name} {token}"
        entity.canonical_name_normalized = f"{entity.canonical_name_normalized} {token}"
    session.add(entity)
    await session.flush()
    return uuid.UUID(str(entity.id))


async def seed_video(
    session: AsyncSession, video_id: str, languages: Sequence[str] = ("en",)
) -> None:
    """Persist a video and one transcript row per language."""
    session.add(
        VideoDB(
            video_id=video_id,
            title=f"Placeholder {video_id}",
            upload_date=datetime(2020, 1, 1, tzinfo=UTC),
            duration=600,
        )
    )
    await session.flush()
    for language in languages:
        session.add(
            VideoTranscriptDB(
                video_id=video_id,
                language_code=language,
                transcript_text="placeholder",
                transcript_type="manual",
                download_reason="user_request",
                is_cc=False,
                is_auto_synced=False,
                track_kind="standard",
                source="youtube_transcript_api",
                has_corrections=False,
                correction_count=0,
                last_corrected_at=None,
            )
        )
    await session.flush()


async def seed_segment(
    session: AsyncSession,
    video_id: str,
    language_code: str,
    start_time: float,
    sequence_number: int,
    *,
    text: str = "placeholder",
    duration: float = 2.0,
) -> int:
    """Persist one transcript segment and return its integer id."""
    segment = TranscriptSegmentDB(
        video_id=video_id,
        language_code=language_code,
        text=text,
        start_time=start_time,
        duration=duration,
        end_time=start_time + duration,
        sequence_number=sequence_number,
    )
    session.add(segment)
    await session.flush()
    return int(segment.id)


async def seed_mention(
    session: AsyncSession,
    *,
    entity_id: uuid.UUID,
    video_id: str,
    language_code: str,
    segment_id: int,
    end_segment_id: int | None = None,
    mention_text: str | None = None,
    detection_method: str = "rule_match",
) -> None:
    """Persist one transcript-source mention anchored at ``segment_id``.

    ``mention_text`` defaults to the entity's canonical (placeholder) name, so the
    mention satisfies the shared visible-name qualification rule (Feature 117). Pass
    a non-name text to seed a mention that should NOT qualify.
    """
    if mention_text is None:
        mention_text = (
            await session.execute(
                select(NamedEntityDB.canonical_name).where(
                    NamedEntityDB.id == entity_id
                )
            )
        ).scalar_one()
    session.add(
        EntityMentionDB(
            entity_id=entity_id,
            segment_id=segment_id,
            end_segment_id=end_segment_id,
            video_id=video_id,
            language_code=language_code,
            mention_text=mention_text,
            detection_method=detection_method,
            mention_source="transcript",
        )
    )
    await session.flush()


async def seed_title_mention(
    session: AsyncSession, *, entity_id: uuid.UUID, video_id: str
) -> None:
    """A title association (no segment, no position): a non-transcript basis."""
    name = (
        await session.execute(
            select(NamedEntityDB.canonical_name).where(NamedEntityDB.id == entity_id)
        )
    ).scalar_one()
    session.add(
        EntityMentionDB(
            entity_id=entity_id,
            video_id=video_id,
            mention_text=name,
            detection_method="rule_match",
            mention_source="title",
        )
    )
    await session.flush()


async def seed_exclusion(
    session: AsyncSession, *, entity_id: uuid.UUID, video_id: str
) -> None:
    """A manual (entity, video) exclusion, as the exclusion tooling records it."""
    session.add(
        EntityVideoExclusionDB(
            entity_id=entity_id,
            video_id=video_id,
            excluded_by="test",
            excluded_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def seed_preference(
    session: AsyncSession,
    *,
    user_id: str,
    language_code: str,
    preference_type: str,
    priority: int,
) -> None:
    """One language preference row for ``user_id``."""
    session.add(
        UserLanguagePreferenceDB(
            user_id=user_id,
            language_code=language_code,
            preference_type=preference_type,
            priority=priority,
        )
    )
    await session.flush()


def canonical(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Order a pair the way the schema stores it (``a < b``)."""
    return (a, b) if a < b else (b, a)


async def seed_pair_in_videos(
    session: AsyncSession,
    *,
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
    video_ids: Sequence[str],
    a_time: float,
    b_time: float,
    language_code: str = "en",
    a_end_time: float | None = None,
) -> list[tuple[int, int]]:
    """Co-mention two entities in every video of ``video_ids``.

    Creates each video (single transcript language), one segment per mention at
    the given start times, and the transcript mentions. When ``a_end_time`` is
    given, A's mention is cross-segment: ``segment_id`` is the start segment
    (``a_time``) and ``end_segment_id`` the segment at ``a_end_time``. Returns the
    ``(segment_a_id, segment_b_id)`` start segments, one pair per video, in order.
    """
    segments: list[tuple[int, int]] = []
    for video_id in video_ids:
        await seed_video(session, video_id, (language_code,))
        seg_a = await seed_segment(session, video_id, language_code, a_time, 0)
        seg_b = await seed_segment(session, video_id, language_code, b_time, 1)
        end_seg: int | None = None
        if a_end_time is not None:
            end_seg = await seed_segment(
                session, video_id, language_code, a_end_time, 2
            )
        await seed_mention(
            session,
            entity_id=entity_a,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_a,
            end_segment_id=end_seg,
        )
        await seed_mention(
            session,
            entity_id=entity_b,
            video_id=video_id,
            language_code=language_code,
            segment_id=seg_b,
        )
        segments.append((seg_a, seg_b))
    return segments


async def seed_scope_state(
    session: AsyncSession,
    *,
    video_id: str,
    language_code: str,
    state: str,
    rule_version: str = MEASUREMENT_RULE_VERSION,
    attempts: int = 0,
) -> None:
    """Persist one ``proximity_scope_states`` row in a given state.

    ``state`` is ``"not_computed"`` (no published result), ``"current"`` (published
    from the latest revision under ``rule_version``), ``"stale"`` (published from an
    older revision), or ``"failing"`` (not computed, ``attempts`` failures under
    ``rule_version``; pass ``attempts`` >= 3 for the flagged case).
    """
    row = ProximityScopeStateDB(
        video_id=video_id, language_code=language_code, revision=2, attempts=attempts
    )
    if state == "current":
        row.computed_revision, row.computed_rule_version = 2, rule_version
        row.computed_at = datetime.now(UTC)
    elif state == "stale":
        row.computed_revision, row.computed_rule_version = 1, rule_version
        row.computed_at = datetime.now(UTC)
    elif state == "failing":
        row.failed_rule_version = rule_version
        row.last_error = "seeded failure"
    elif state != "not_computed":
        raise ValueError(f"unknown scope state {state!r}")
    session.add(row)
    await session.flush()


async def measure_scope(
    session: AsyncSession, *, video_id: str, language_code: str
) -> int:
    """Compute one scope's records through the real path and mark it current.

    Records come from ``replace_scope_records`` (the production INSERT...SELECT), so a
    test exercises the shared qualification rule and exclusions rather than
    hand-inserted rows. Any existing state row for the scope is replaced by a current
    one. Returns the number of records written.
    """
    written = await EntityPairProximityRepository().replace_scope_records(
        session,
        video_id=video_id,
        language_code=language_code,
        outer_window=OUTER_WINDOW_SECONDS,
    )
    await session.execute(
        delete(ProximityScopeStateDB).where(
            ProximityScopeStateDB.video_id == video_id,
            ProximityScopeStateDB.language_code == language_code,
        )
    )
    await seed_scope_state(
        session, video_id=video_id, language_code=language_code, state="current"
    )
    return written


async def seed_timed_comentions(
    session: AsyncSession,
    *,
    entity_a: uuid.UUID,
    entity_b: uuid.UUID,
    video_id: str,
    moments: Sequence[tuple[float, float]],
    language_code: str = "en",
    create_video: bool = True,
    measure: bool = True,
) -> list[tuple[int, int]]:
    """Co-mention two entities at explicit times in one video and language.

    Each ``(a_time, b_time)`` becomes a segment per distinct time (one segment when the
    two times are equal) carrying qualifying mentions, with sequence numbers in
    insertion order. Segment text names the entity it carries, so highlights can be
    asserted. With ``create_video=False`` the video and transcript row must exist
    (seed several languages with :func:`seed_video` first). With ``measure=True`` the
    scope is then computed through :func:`measure_scope`. Returns the
    ``(segment_a_id, segment_b_id)`` of each moment, in order.
    """
    if create_video:
        await seed_video(session, video_id, (language_code,))
    names = dict(
        (
            await session.execute(
                select(NamedEntityDB.id, NamedEntityDB.canonical_name).where(
                    NamedEntityDB.id.in_([entity_a, entity_b])
                )
            )
        )
        .tuples()
        .all()
    )
    next_seq = (
        await session.execute(
            select(
                func.coalesce(func.max(TranscriptSegmentDB.sequence_number), -1)
            ).where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.language_code == language_code,
            )
        )
    ).scalar_one() + 1
    segments: list[tuple[int, int]] = []
    for a_time, b_time in moments:
        if a_time == b_time:
            shared = await seed_segment(
                session,
                video_id,
                language_code,
                a_time,
                next_seq,
                text=f"{names[entity_a]} and {names[entity_b]}",
            )
            next_seq += 1
            seg_a = seg_b = shared
        else:
            seg_a = await seed_segment(
                session, video_id, language_code, a_time, next_seq, text=names[entity_a]
            )
            seg_b = await seed_segment(
                session,
                video_id,
                language_code,
                b_time,
                next_seq + 1,
                text=names[entity_b],
            )
            next_seq += 2
        for entity_id, segment_id in ((entity_a, seg_a), (entity_b, seg_b)):
            await seed_mention(
                session,
                entity_id=entity_id,
                video_id=video_id,
                language_code=language_code,
                segment_id=segment_id,
            )
        segments.append((seg_a, seg_b))
    if measure:
        await measure_scope(session, video_id=video_id, language_code=language_code)
    return segments


LogicalRecord = tuple[uuid.UUID, uuid.UUID, str, str, int, int, float]


async def logical_records(session: AsyncSession) -> set[LogicalRecord]:
    """All co-mention records by logical key (excludes generated ``id``/``computed_at``).

    The gap is rounded to microseconds so float round-trips compare equal. Used to
    assert incremental maintenance equals a full rebuild (SC-003).
    """
    rows = await session.execute(
        select(
            EntityPairProximityDB.entity_a_id,
            EntityPairProximityDB.entity_b_id,
            EntityPairProximityDB.video_id,
            EntityPairProximityDB.language_code,
            EntityPairProximityDB.segment_a_id,
            EntityPairProximityDB.segment_b_id,
            EntityPairProximityDB.gap_seconds,
        )
    )
    return {(r[0], r[1], r[2], r[3], r[4], r[5], round(r[6], 6)) for r in rows.all()}
