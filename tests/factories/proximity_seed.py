"""Seeding helpers for Feature 116 (transcript proximity) integration tests.

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
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from tests.factories.named_entity_orm_factory import create_named_entity_db


class _SessionScope:
    """Stand-in for ``db_manager`` that yields one fixed session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def session(self, echo: bool | None = None) -> AsyncIterator[AsyncSession]:
        yield self._session
        await self._session.flush()


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
) -> int:
    """Persist one transcript segment and return its integer id."""
    segment = TranscriptSegmentDB(
        video_id=video_id,
        language_code=language_code,
        text="placeholder",
        start_time=start_time,
        duration=2.0,
        end_time=start_time + 2.0,
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
) -> None:
    """Persist one transcript-source mention anchored at ``segment_id``."""
    session.add(
        EntityMentionDB(
            entity_id=entity_id,
            segment_id=segment_id,
            end_segment_id=end_segment_id,
            video_id=video_id,
            language_code=language_code,
            mention_text="placeholder",
            detection_method="rule_match",
            mention_source="transcript",
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
) -> None:
    """Co-mention two entities in every video of ``video_ids``.

    Creates each video (single transcript language), one segment per mention at
    the given start times, and the transcript mentions. When ``a_end_time`` is
    given, A's mention is cross-segment: ``segment_id`` is the start segment
    (``a_time``) and ``end_segment_id`` the segment at ``a_end_time``.
    """
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
