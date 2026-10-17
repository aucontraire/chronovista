"""Integration test for cross-segment mention detection (Feature 081, T012/T013).

End-to-end against a real PostgreSQL database (db_session fixture). Seeds one video
whose entity name is split across a segment boundary AND a single-segment control, then
runs the full scan and asserts: exactly one spanning mention (anchored first→last) is
recovered, and the single-segment match stays a normal mention with end_segment_id NULL
(FR-006). Neutral placeholder names only (Constitution VI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.id_factory import channel_id, video_id

pytestmark = __import__("pytest").mark.asyncio

CH = channel_id(seed="xseg")
VID = video_id(seed="xseg_1")


def _factory(session: AsyncSession) -> Any:
    class _CM:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *a: object) -> bool:
            return False

    class _F:
        def __call__(self) -> _CM:
            return _CM()

    return _F()


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, int, int, int]:
    session.add(
        ChannelDB(channel_id=CH, title="C", description="d", is_subscribed=False)
    )
    await session.flush()
    session.add(
        VideoDB(
            video_id=VID,
            channel_id=CH,
            title="V",
            description="d",
            upload_date=datetime(2024, 1, 1, tzinfo=UTC),
            duration=120,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
    )
    await session.flush()
    session.add(
        VideoTranscriptDB(
            video_id=VID,
            language_code="en",
            transcript_text="",
            transcript_type="auto",
            download_reason="user_request",
            is_cc=False,
            is_auto_synced=True,
            track_kind="standard",
            source="youtube_transcript_api",
        )
    )
    await session.flush()

    def _seg(seq: int, body: str) -> TranscriptSegmentDB:
        return TranscriptSegmentDB(
            video_id=VID,
            language_code="en",
            text=body,
            has_correction=False,
            start_time=float(seq),
            duration=1.0,
            end_time=float(seq) + 1.0,
            sequence_number=seq,
        )

    # seq 0/1: the name "Foo Bar" is split across the boundary.
    # seq 2: a single-segment control containing the whole name.
    s0 = _seg(0, "the guest is Foo")
    s1 = _seg(1, "Bar is speaking")
    s2 = _seg(2, "later Foo Bar returned")
    session.add_all([s0, s1, s2])
    await session.flush()

    entity = NamedEntityDB(
        canonical_name="Foo Bar",
        canonical_name_normalized="foo bar",
        entity_type="person",
        status="active",
        discovery_method="manual",
        confidence=1.0,
        mention_count=0,
        video_count=0,
    )
    session.add(entity)
    await session.flush()
    session.add(
        EntityAliasDB(
            entity_id=entity.id,
            alias_name="Foo Bar",
            alias_name_normalized="foo bar",
            alias_type="name_variant",
            occurrence_count=0,
        )
    )
    await session.flush()
    await session.commit()
    return entity.id, s0.id, s1.id, s2.id


class TestCrossSegmentIntegration:
    async def test_spanning_recovered_single_segment_unchanged(
        self, db_session: AsyncSession
    ) -> None:
        entity_id, s0, s1, s2 = await _seed(db_session)
        svc = EntityMentionScanService(session_factory=_factory(db_session))

        await svc.scan(video_ids=[VID], full_rescan=True)

        rows = (
            (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == entity_id,
                        EntityMentionDB.mention_source == "transcript",
                    )
                )
            )
            .scalars()
            .all()
        )

        spanning = [r for r in rows if r.end_segment_id is not None]
        single = [r for r in rows if r.end_segment_id is None]

        # Exactly one spanning mention, anchored first -> last (T012).
        assert len(spanning) == 1
        span = spanning[0]
        assert span.segment_id == s0
        assert span.end_segment_id == s1
        assert span.mention_text == "Foo Bar"
        assert span.detection_method == "rule_match"
        assert span.mention_context is not None and "Foo" in span.mention_context

        # The single-segment control is detected normally, end_segment_id NULL (FR-006).
        assert len(single) == 1
        assert single[0].segment_id == s2
        assert single[0].end_segment_id is None

    async def test_rescan_is_idempotent_for_spanning(
        self, db_session: AsyncSession
    ) -> None:
        entity_id, s0, s1, _s2 = await _seed(db_session)
        svc = EntityMentionScanService(session_factory=_factory(db_session))

        await svc.scan(video_ids=[VID], full_rescan=True)
        await svc.scan(video_ids=[VID], full_rescan=True)

        spanning = (
            (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == entity_id,
                        EntityMentionDB.end_segment_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(spanning) == 1  # not duplicated on a second --full rescan
