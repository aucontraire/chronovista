"""Integration tests for the whitespace-normalization backfill (#293, US3).

End-to-end against a real PostgreSQL database (db_session fixture). Verifies,
after a normalize + re-scan of a seeded affected video, that every consumer of
segment text is consistent: display text is clean, entity-mention offsets slice
back to a clean mention_text, manual mentions survive, transcript search still
finds the segment, and the operation is idempotent.

Neutral placeholder names only.
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
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from chronovista.services.transcript_whitespace_service import (
    TranscriptWhitespaceBackfillService,
)
from tests.factories.id_factory import channel_id, video_id

pytestmark = __import__("pytest").mark.asyncio

CH = channel_id(seed="ws_bf")
VID = video_id(seed="ws_bf_1")


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


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, int]:
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
    # A segment where a two-word entity name is split by a newline artifact.
    seg = TranscriptSegmentDB(
        video_id=VID,
        language_code="en",
        text="visited Foo\nBar today",
        has_correction=False,
        start_time=0.0,
        duration=5.0,
        end_time=5.0,
        sequence_number=0,
    )
    session.add(seg)
    await session.flush()
    entity = NamedEntityDB(
        canonical_name="Foo Bar",
        canonical_name_normalized="foo bar",
        entity_type="organization",
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
    # A hand-made mention that must survive the re-scan.
    session.add(
        EntityMentionDB(
            entity_id=entity.id,
            video_id=VID,
            segment_id=seg.id,
            mention_text="Foo Bar",
            detection_method="manual",
            confidence=1.0,
        )
    )
    await session.flush()
    await session.commit()
    return entity.id, seg.id


class TestWhitespaceBackfillIntegration:
    async def test_normalize_rescan_through_all_consumers(
        self, db_session: AsyncSession
    ) -> None:
        entity_id, seg_id = await _seed(db_session)
        factory = _factory(db_session)
        service = TranscriptWhitespaceBackfillService(
            factory, scan_service=EntityMentionScanService(session_factory=factory)
        )

        summary = await service.run(apply=True, video_id=VID)
        assert summary.segments_normalized == 1

        # 1. Display: stored text is clean (newline collapsed).
        seg = await db_session.get(TranscriptSegmentDB, seg_id)
        assert seg is not None and seg.text == "visited Foo Bar today"

        mentions = (await db_session.execute(select(EntityMentionDB))).scalars().all()
        by_method: dict[str, list[EntityMentionDB]] = {}
        for m in mentions:
            by_method.setdefault(m.detection_method, []).append(m)

        # 2. Manual mention preserved.
        assert len(by_method.get("manual", [])) == 1

        # 3. A rule_match mention now exists, clean, with offsets that slice
        #    back to its mention_text against the normalized segment text.
        rule = by_method.get("rule_match", [])
        assert len(rule) == 1
        rm = rule[0]
        assert rm.mention_text == "Foo Bar"  # clean, from re-scan on normalized text
        assert seg.text[rm.match_start : rm.match_end] == rm.mention_text

        # 4. Search: the segment is still found by a term in the normalized text.
        repo = TranscriptSegmentRepository()
        found = await repo.find_by_text_pattern(db_session, pattern="Foo Bar")
        assert any(s.id == seg_id for s in found)

    async def test_idempotent_second_run(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        factory = _factory(db_session)
        service = TranscriptWhitespaceBackfillService(
            factory, scan_service=EntityMentionScanService(session_factory=factory)
        )
        await service.run(apply=True, video_id=VID)
        # A second apply changes nothing.
        again = await service.run(apply=True, video_id=VID)
        assert again.segments_normalized == 0

    async def test_dry_run_writes_nothing(self, db_session: AsyncSession) -> None:
        _entity_id, seg_id = await _seed(db_session)
        factory = _factory(db_session)
        service = TranscriptWhitespaceBackfillService(
            factory, scan_service=EntityMentionScanService(session_factory=factory)
        )
        summary = await service.run(apply=False, video_id=VID)
        assert summary.dry_run is True
        assert summary.segments_normalized == 1
        seg = await db_session.get(TranscriptSegmentDB, seg_id)
        assert seg is not None and seg.text == "visited Foo\nBar today"  # untouched

    async def test_dry_run_count_is_transcript_only(
        self, db_session: AsyncSession
    ) -> None:
        # The dry-run projection must count only transcript-source rule_match
        # mentions (what --apply regenerates), not title/description ones.
        entity_id, _seg_id = await _seed(db_session)
        db_session.add(
            EntityMentionDB(
                entity_id=entity_id,
                video_id=VID,
                segment_id=None,
                mention_text="Foo Bar",
                detection_method="rule_match",
                mention_source="transcript",
                confidence=1.0,
            )
        )
        await db_session.flush()
        db_session.add(
            EntityMentionDB(
                entity_id=entity_id,
                video_id=VID,
                segment_id=None,
                mention_text="Foo Bar",
                detection_method="rule_match",
                mention_source="title",  # must be excluded from the projection
                confidence=1.0,
            )
        )
        await db_session.flush()
        await db_session.commit()

        factory = _factory(db_session)
        service = TranscriptWhitespaceBackfillService(
            factory, scan_service=EntityMentionScanService(session_factory=factory)
        )
        summary = await service.run(apply=False, video_id=VID)
        # Only the transcript rule_match mention is counted (not the title one,
        # not the manual one seeded by _seed).
        assert summary.mentions_regenerated == 1
