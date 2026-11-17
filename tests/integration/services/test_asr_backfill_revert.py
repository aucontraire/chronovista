"""Integration test: the ASR backfill is revertible (T034 / SC-009).

Feature 111 writes recovered ASR-error-form mentions with
``detection_method='asr_match'``. The backfill's safety guarantee (SC-009) is
that it is cleanly revertible: ``DELETE WHERE detection_method='asr_match'``
restores the *exact* pre-backfill mention set, touching nothing else.

Counters are the exception: the scan also updates ``named_entities.mention_count``
/ ``video_count`` (``EntityMentionRepository.update_entity_counters``), and a bare
DELETE does NOT recompute them. A COMPLETE revert is therefore
``DELETE WHERE detection_method='asr_match'`` plus a counter recompute (or a
rescan, which recomputes). The DELETE alone restores rows but not counters.

This proves it end-to-end against a real database with a three-step sequence:

1. **Pre-backfill scan** — before any ASR-error form is registered. The only
   match is a genuine canonical-name occurrence (a ``rule_match``). Snapshot that
   set S0 as id-independent logical tuples ``(segment_id, entity_id,
   lower(text), detection_method)``.
2. **Backfill** — register a distinctive multi-word ASR garble (folds away from
   the canonical name, so it is admitted as ``asr_match`` rather than colliding
   with a real name) in a SEPARATE, non-overlapping segment, then ``--full``
   rescan. Assert ``asr_match`` rows now exist and the non-asr subset still
   equals S0 (the backfill only ADDED recovered rows; the baseline is intact).
3. **Revert** — ``DELETE WHERE detection_method='asr_match'`` and assert the
   remaining set equals S0 exactly, with zero ``asr_match`` rows left; assert
   ``mention_count`` is still stale, then recompute counters and assert it
   equals the pre-backfill value.

All seed strings are deliberately INVENTED (no real entity names or ASR garble).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAsrError as EntityAsrErrorDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.enums import DetectionMethod
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.id_factory import channel_id, video_id

pytestmark = pytest.mark.asyncio

_CHANNEL_ID = channel_id(seed="asr_revert")
_VIDEO_ID = video_id(seed="asr_revert_1")

# Invented strings only. The garble folds away from the canonical name, so it is
# admitted as a recovered asr_match rather than colliding with the real name.
_CANONICAL_NAME = "Thessaly Brandt"
_ADMISSIBLE_ASR = "thesserly brant"  # multi-word, distinctive -> asr_match


async def _seed_scaffolding(session: AsyncSession) -> None:
    """Insert the channel / video / transcript FK chain the scan needs."""
    session.add(
        ChannelDB(
            channel_id=_CHANNEL_ID,
            title="Invented Channel",
            description="ASR revert integration test channel",
            is_subscribed=False,
        )
    )
    await session.flush()
    session.add(
        VideoDB(
            video_id=_VIDEO_ID,
            channel_id=_CHANNEL_ID,
            title="Invented Video",
            description="ASR revert integration test video",
            upload_date=datetime(2024, 1, 1, tzinfo=UTC),
            duration=120,
            made_for_kids=False,
            self_declared_made_for_kids=False,
        )
    )
    await session.flush()
    session.add(
        VideoTranscriptDB(
            video_id=_VIDEO_ID,
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


async def _seed_segment(
    session: AsyncSession, text: str, sequence_number: int
) -> TranscriptSegmentDB:
    """Insert one transcript segment carrying ``text``."""
    seg = TranscriptSegmentDB(
        video_id=_VIDEO_ID,
        language_code="en",
        text=text,
        has_correction=False,
        start_time=float(sequence_number * 5),
        duration=5.0,
        end_time=float(sequence_number * 5 + 5),
        sequence_number=sequence_number,
    )
    session.add(seg)
    await session.flush()
    return seg


def _make_session_factory_from_session(session: AsyncSession) -> Any:
    """Return a fake async_sessionmaker that always yields ``session``.

    Lets the service share the test-managed session so writes are visible to the
    assertions in the same transaction (mirrors the scan integration suite).
    """

    class _FakeContextManager:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *args: object) -> bool:
            return False

    class _FakeFactory:
        def __call__(self) -> _FakeContextManager:
            return _FakeContextManager()

    return _FakeFactory()


async def _snapshot(
    session: AsyncSession,
) -> set[tuple[int | None, uuid.UUID, str, str]]:
    """Id-independent logical fingerprint of the current mention set.

    Row ids change across a ``--full`` re-mint (delete + re-insert), so identity
    is the stable tuple of what a mention IS, not its uuid. ``segment_id`` is a
    nullable column (hence ``int | None``); for these transcript mentions it is
    always populated, but the type mirrors the model.
    """
    rows = (await session.execute(select(EntityMentionDB))).scalars().all()
    return {
        (r.segment_id, r.entity_id, r.mention_text.lower(), r.detection_method)
        for r in rows
    }


async def _asr_count(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    EntityMentionDB.detection_method == DetectionMethod.ASR_MATCH.value
                )
            )
        ).scalar()
        or 0
    )


@pytest.mark.db
@pytest.mark.integration
class TestAsrBackfillRevert:
    """SC-009: deleting asr_match rows restores the exact pre-backfill snapshot."""

    async def test_delete_asr_match_restores_pre_backfill_snapshot(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_scaffolding(db_session)

        entity = NamedEntityDB(
            canonical_name=_CANONICAL_NAME,
            canonical_name_normalized=_CANONICAL_NAME.lower(),
            entity_type="person",
            status="active",
            discovery_method="manual",
            confidence=1.0,
            mention_count=0,
            video_count=0,
        )
        db_session.add(entity)
        await db_session.flush()

        # Two NON-overlapping segments: the canonical name (seg 0) and, separately,
        # the ASR garble (seg 1). Keeping them apart makes ASR admission purely
        # additive — it never suppresses the baseline rule_match mention.
        await _seed_segment(db_session, f"{_CANONICAL_NAME} appears here", 0)
        await _seed_segment(db_session, f"{_ADMISSIBLE_ASR} appears here", 1)
        await db_session.commit()

        service = EntityMentionScanService(
            session_factory=_make_session_factory_from_session(db_session)
        )

        # (1) Pre-backfill scan: ASR form NOT yet registered, so the garble segment
        # matches nothing. The snapshot is the genuine canonical rule_match only.
        await service.scan(full_rescan=True)
        pre_backfill = await _snapshot(db_session)
        assert pre_backfill, "pre-backfill scan must detect the canonical name"
        await db_session.refresh(entity)
        pre_backfill_mention_count = entity.mention_count
        assert pre_backfill_mention_count >= 1, "scan must have counted the mention"
        assert (
            await _asr_count(db_session) == 0
        ), "no asr_match rows must exist before the ASR form is registered"
        assert all(
            method == DetectionMethod.RULE_MATCH.value
            for *_rest, method in pre_backfill
        ), "the pre-backfill snapshot must be rule_match only"

        # (2) Backfill: register the distinctive garble, then --full rescan. The
        # recovery adds asr_match rows; the baseline (non-asr) subset is unchanged.
        db_session.add(
            EntityAsrErrorDB(
                entity_id=entity.id,
                alias_name=_ADMISSIBLE_ASR,
                alias_name_normalized=_ADMISSIBLE_ASR.lower(),
            )
        )
        await db_session.commit()

        await service.scan(full_rescan=True)
        assert (
            await _asr_count(db_session) >= 1
        ), "the backfill must recover at least one asr_match mention"
        post_backfill = await _snapshot(db_session)
        non_asr_after_backfill = {
            t for t in post_backfill if t[3] != DetectionMethod.ASR_MATCH.value
        }
        assert non_asr_after_backfill == pre_backfill, (
            "the backfill changed a non-asr mention — it must only ADD asr_match "
            "rows, leaving the pre-backfill baseline byte-for-byte intact"
        )
        assert (
            post_backfill != pre_backfill
        ), "sanity: the backfill must actually have added asr_match rows"

        # (3) Revert: DELETE WHERE detection_method='asr_match'. The remaining set
        # must equal the pre-backfill snapshot EXACTLY, with no asr_match left.
        await db_session.execute(
            delete(EntityMentionDB).where(
                EntityMentionDB.detection_method == DetectionMethod.ASR_MATCH.value
            )
        )
        await db_session.commit()

        assert (
            await _asr_count(db_session) == 0
        ), "revert must remove all asr_match rows"
        assert await _snapshot(db_session) == pre_backfill, (
            "DELETE WHERE detection_method='asr_match' did not restore the exact "
            "pre-backfill snapshot — the backfill is not cleanly revertible (SC-009)"
        )

        # A bare DELETE restores rows but NOT counters: mention_count is stale.
        await db_session.refresh(entity)
        assert entity.mention_count > pre_backfill_mention_count, (
            "expected mention_count to remain elevated after a bare DELETE; if "
            "this fails the DELETE recomputes counters and the recompute below "
            "is redundant"
        )

        # Complete revert = DELETE + counter recompute.
        await EntityMentionRepository().update_entity_counters(db_session, [entity.id])
        await db_session.commit()
        await db_session.refresh(entity)
        assert entity.mention_count == pre_backfill_mention_count, (
            "counter recompute did not restore the pre-backfill mention_count "
            "(SC-009)"
        )
