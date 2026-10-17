"""Convergence invariant for cross-segment mentions (Feature 081, US2 / SC-007).

A single spanning occurrence must count as exactly ONE on every surface that reports an
occurrence count — never two, even though the mention touches two segments. This guards the
cross-surface count divergence seen in prior features (#321). The surface with real +2 risk
is ``get_video_entity_summary`` (``COUNT(DISTINCT segment_id)``): it must count the span via
its START segment only. Neutral placeholder names only (Constitution VI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.id_factory import channel_id, video_id

pytestmark = __import__("pytest").mark.asyncio

CH = channel_id(seed="xcvg")
VID = video_id(seed="xcvg_1")


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


async def _seed_single_span(session: AsyncSession) -> tuple[uuid.UUID, int, int]:
    """Seed a transcript whose only occurrence of the entity is ONE boundary-split name."""
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

    # "Foo Bar" split across seq 0/1 — the ONLY occurrence in this transcript.
    s0 = _seg(0, "the guest is Foo")
    s1 = _seg(1, "Bar is speaking")
    session.add_all([s0, s1])
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
    return entity.id, s0.id, s1.id


class TestConvergenceInvariant:
    async def test_single_span_counts_as_one_everywhere(
        self, db_session: AsyncSession
    ) -> None:
        entity_id, s0, s1 = await _seed_single_span(db_session)
        svc = EntityMentionScanService(session_factory=_factory(db_session))
        await svc.scan(video_ids=[VID], full_rescan=True)

        # The span exists, touches BOTH segments, but is ONE row.
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
        assert len(rows) == 1
        assert (rows[0].segment_id, rows[0].end_segment_id) == (s0, s1)

        repo = EntityMentionRepository()

        # Surface A — denormalized named_entities.mention_count (DISTINCT mention id),
        # recomputed by the scan. Feeds entity detail/list endpoints.
        await repo.update_entity_counters(db_session, [entity_id])
        entity = await db_session.get(NamedEntityDB, entity_id)
        assert entity is not None
        assert entity.mention_count == 1
        assert entity.video_count == 1

        # Surface B — the DISTINCT-segment_id surface (the real +2 risk). MUST be 1:
        # the span counts via its START segment only, not both crossed segments.
        summary = await repo.get_video_entity_summary(db_session, VID)
        mine = [d for d in summary if d["entity_id"] == str(entity_id)]
        assert len(mine) == 1
        assert mine[0]["mention_count"] == 1

        # Surface C — raw row count of transcript mentions (per-video list style): 1.
        row_count = await db_session.scalar(
            select(func.count())
            .select_from(EntityMentionDB)
            .where(
                EntityMentionDB.entity_id == entity_id,
                EntityMentionDB.mention_source == "transcript",
            )
        )
        assert row_count == 1

        # Convergence: every occurrence surface agrees on 1; none double-counts the span.
        assert entity.mention_count == mine[0]["mention_count"] == row_count == 1
