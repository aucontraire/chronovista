"""Integration tests for correction-created cross-segment mentions (Feature 081, T024/T025).

End-to-end against a real PostgreSQL database (``db_session`` fixture). A correction that
distributes a two-token name across a segment boundary (T026) must record the occurrence
as exactly ONE spanning ``user_correction`` mention (anchored first -> last), via the same
span-resolution primitive the detection scanner uses (FR-013/FR-016) — never two
per-segment rows. Reverting EITHER paired segment must remove that spanning mention through
the correction cascade (FR-009). Neutral placeholder names only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

# A stdlib UUID (production uses ``uuid.UUID(bytes=uuid7().bytes)``; the raw
# ``uuid_utils.UUID`` is not a ``uuid.UUID`` subclass and Pydantic rejects it).
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.enums import CorrectionType
from chronovista.services.batch_correction_service import BatchCorrectionService
from tests.factories.id_factory import video_id

from .test_cross_segment_corrections import (
    _make_batch_service,
    _seed_channel,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

pytestmark = __import__("pytest").mark.asyncio

# The corrected two-token name distributed across the boundary.
NAME = "Alfa Bravo"


async def _seed_entity(session: AsyncSession) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=NAME,
        canonical_name_normalized=NAME.lower(),
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
            alias_name=NAME,
            alias_name_normalized=NAME.lower(),
            alias_type="name_variant",
            occurrence_count=0,
        )
    )
    await session.flush()
    return entity.id


async def _apply_cross_segment_name_correction(
    db_session: AsyncSession,
    service: BatchCorrectionService,
    entity_id: uuid.UUID,
    vid: str,
) -> None:
    """Find the boundary-spanning garble and correct it to ``NAME`` with mentions on."""
    entity = await db_session.get(NamedEntityDB, entity_id)
    matches = await service._find_cross_segment_matches(
        db_session,
        pattern="Alpha Bravado",
        replacement=NAME,
        regex=False,
        case_insensitive=False,
        re_flags=0,
        language="en",
        channel=None,
        video_ids=[vid],
        single_segment_ids=set(),
    )
    assert len(matches) == 1, f"expected one cross-segment match, got {len(matches)}"
    await service._apply_cross_segment_corrections(
        db_session,
        matches,
        correction_type=CorrectionType.PROPER_NOUN,
        correction_note=None,
        batch_size=100,
        entity=entity,
        replacement=NAME,
        batch_id=uuid.UUID(bytes=uuid7().bytes),
    )


async def _seed_split_pair(
    db_session: AsyncSession, vid: str
) -> tuple[uuid.UUID, int, int]:
    await _seed_channel(db_session)
    await _seed_video(db_session, vid)
    await _seed_transcript(db_session, vid, language_code="en")
    seg_a = await _seed_segment(
        db_session,
        vid_id=vid,
        language_code="en",
        sequence_number=0,
        text="the guest is Alpha",
        start_time=0.0,
    )
    # The trailing token is garbled ("Bravado"), so correcting it changes BOTH
    # segments — without this, seg B's distributed text would equal its original
    # and B would carry no correction to cascade a revert from.
    seg_b = await _seed_segment(
        db_session,
        vid_id=vid,
        language_code="en",
        sequence_number=1,
        text="Bravado speaks",
        start_time=5.0,
    )
    entity_id = await _seed_entity(db_session)
    await db_session.commit()
    return entity_id, seg_a.id, seg_b.id


async def _spanning_mentions(
    db_session: AsyncSession, entity_id: uuid.UUID
) -> list[Any]:
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
    return list(rows)


class TestCorrectionCreatesOneSpanningMention:
    async def test_distributed_correction_records_single_spanning_mention(
        self, db_session: AsyncSession
    ) -> None:
        vid = video_id(seed="x081cm_one")
        entity_id, s_a, s_b = await _seed_split_pair(db_session, vid)
        service = _make_batch_service()

        await _apply_cross_segment_name_correction(db_session, service, entity_id, vid)

        rows = await _spanning_mentions(db_session, entity_id)
        # Exactly one row for the occurrence — not two per-segment rows.
        assert len(rows) == 1
        m = rows[0]
        assert (m.segment_id, m.end_segment_id) == (s_a, s_b)
        assert m.detection_method == "user_correction"
        assert m.correction_id is not None
        assert m.mention_text == NAME

        # The name really is split across the boundary (T026): neither segment holds
        # the whole name, which is why one spanning row — not a per-segment row — is right.
        seg_a = await db_session.get(TranscriptSegmentDB, s_a)
        seg_b = await db_session.get(TranscriptSegmentDB, s_b)
        assert seg_a is not None and seg_b is not None
        text_a = seg_a.corrected_text or seg_a.text
        text_b = seg_b.corrected_text or seg_b.text
        assert "Alfa" in text_a and "Bravo" not in text_a
        assert "Bravo" in text_b and "Alfa" not in text_b


class TestRevertRemovesSpanningMention:
    async def test_revert_via_first_segment_removes_span(
        self, db_session: AsyncSession
    ) -> None:
        vid = video_id(seed="x081cm_rva")
        entity_id, s_a, s_b = await _seed_split_pair(db_session, vid)
        service = _make_batch_service()
        await _apply_cross_segment_name_correction(db_session, service, entity_id, vid)
        assert len(await _spanning_mentions(db_session, entity_id)) == 1

        # Reverting on seg A's fragment cascades to partner B and drops the span.
        await service.batch_revert(db_session, pattern="Alfa", video_ids=[vid])

        assert await _spanning_mentions(db_session, entity_id) == []
        seg_a = await db_session.get(TranscriptSegmentDB, s_a)
        seg_b = await db_session.get(TranscriptSegmentDB, s_b)
        assert seg_a is not None and not seg_a.has_correction
        assert seg_b is not None and not seg_b.has_correction

    async def test_revert_via_second_segment_removes_span(
        self, db_session: AsyncSession
    ) -> None:
        vid = video_id(seed="x081cm_rvb")
        entity_id, s_a, s_b = await _seed_split_pair(db_session, vid)
        service = _make_batch_service()
        await _apply_cross_segment_name_correction(db_session, service, entity_id, vid)
        assert len(await _spanning_mentions(db_session, entity_id)) == 1

        # Reverting on seg B's fragment cascades to partner A and drops the same span.
        await service.batch_revert(db_session, pattern="Bravo", video_ids=[vid])

        assert await _spanning_mentions(db_session, entity_id) == []
        seg_a = await db_session.get(TranscriptSegmentDB, s_a)
        seg_b = await db_session.get(TranscriptSegmentDB, s_b)
        assert seg_a is not None and not seg_a.has_correction
        assert seg_b is not None and not seg_b.has_correction
