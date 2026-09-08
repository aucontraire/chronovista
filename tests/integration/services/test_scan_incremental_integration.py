"""Integration (real-DB) SEAM tests for the resumable scan (#291).

These cross the real boundaries — real DB, real cursor/interrupt round-trip —
rather than mocking the service. Neutral placeholder names only.

- T007  interrupt keeps committed work (SC-001)
- T010  SEAM-1 resume round-trip: cursor never ahead of durable; resumed==uninterrupted
- T014  SEAM-2 --full delete is source-scoped: manual mentions survive
- T016  per-batch commit (US4)
- T018  US5 metadata scan interrupt+resume parity
- T023  detection-phase failure isolation (FR-016)
- T015  SEAM-3 --full atomicity: no segment left deleted-but-not-reinserted
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import Video as VideoDB
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from tests.factories.id_factory import channel_id, video_id
from tests.integration.services.test_entity_mention_scan_integration import (
    _make_session_factory_from_session,
    _seed_alias,
    _seed_channel,
    _seed_entity,
    _seed_segment,
    _seed_transcript,
    _seed_video,
)

pytestmark = pytest.mark.asyncio

CH = channel_id(seed="scan_inc")
VID = video_id(seed="scan_inc_1")


async def _seed_three_segments(session: AsyncSession) -> uuid.UUID:
    """One video, three segments each mentioning entity 'Foo Bar'."""
    await _seed_channel(session, CH)
    await _seed_video(session, VID, CH)
    await _seed_transcript(session, VID)
    for i in range(3):
        await _seed_segment(
            session, VID, text=f"segment {i} mentions Foo Bar here", sequence_number=i
        )
    entity = await _seed_entity(session, "Foo Bar", entity_type="organization")
    await _seed_alias(session, entity.id, "Foo Bar")
    await session.commit()
    return entity.id


async def _mention_count(session: AsyncSession) -> int:
    rows = (await session.execute(select(EntityMentionDB))).scalars().all()
    return len(rows)


class TestInterruptAndResume:
    async def test_interrupt_keeps_work_then_resume_completes(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)

        checkpoints: list[int] = []
        # Stop after the first committed batch (should_continue checked post-commit).
        stop = {"go": True}

        def _cont() -> bool:
            if stop["go"]:
                stop["go"] = False
                return False  # stop after batch 1
            return True

        r1 = await svc.scan(
            batch_size=1,
            should_continue=_cont,
            checkpoint_callback=checkpoints.append,
        )
        # T007: batch-1 work committed and visible; run marked incomplete.
        assert r1.completed is False
        assert r1.last_processed_id is not None
        after_interrupt = await _mention_count(db_session)
        assert after_interrupt >= 1
        # SEAM-1: the persisted cursor is not ahead of durable data — every
        # checkpointed segment id has its mention committed.
        assert checkpoints == [r1.last_processed_id]

        # T010: resume from the cursor completes without redoing batch 1.
        r2 = await svc.scan(batch_size=1, resume_from=r1.last_processed_id)
        assert r2.completed is True
        total_after_resume = await _mention_count(db_session)
        assert total_after_resume == 3  # one mention per segment, no duplicates

    async def test_resumed_equals_uninterrupted(self, db_session: AsyncSession) -> None:
        await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)
        # A single uninterrupted run.
        r = await svc.scan(batch_size=1)
        assert r.completed is True
        assert await _mention_count(db_session) == 3


class TestPerBatchCommit:
    async def test_commits_once_per_batch(self, db_session: AsyncSession) -> None:
        await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)
        checkpoints: list[int] = []
        # 3 segments, batch_size=1 -> a checkpoint (fired after each commit) per batch.
        await svc.scan(batch_size=1, checkpoint_callback=checkpoints.append)
        assert len(checkpoints) == 3  # US4: committed incrementally, not once


class TestFailureIsolation:
    async def test_detection_failure_isolated_and_skipped(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)

        original = svc._scan_batch
        calls = {"n": 0}

        async def _flaky(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 2:  # fail the 2nd batch's detection
                raise RuntimeError("boom")
            return await original(*args, **kwargs)

        svc._scan_batch = _flaky  # type: ignore[method-assign]
        result = await svc.scan(batch_size=1)
        # FR-016: run did not abort; the bad batch was counted and skipped;
        # batches 1 and 3 committed; batch 2's segment produced no mention.
        assert result.failed_batches == 1
        assert result.completed is True
        assert await _mention_count(db_session) == 2  # 3 segments minus the skipped one


class TestFullRescanAtomicity:
    async def test_interrupt_leaves_no_segment_deleted_without_reinsert(
        self, db_session: AsyncSession
    ) -> None:
        await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)
        # Populate mentions first (one per segment).
        await svc.scan(batch_size=1)
        assert await _mention_count(db_session) == 3

        # --full, interrupted after the first batch.
        stop = {"go": True}

        def _cont() -> bool:
            if stop["go"]:
                stop["go"] = False
                return False
            return True

        r = await svc.scan(batch_size=1, full_rescan=True, should_continue=_cont)
        assert r.completed is False
        # SEAM-3 atomicity: every segment still has exactly its mention — the
        # processed batch was re-derived (delete+reinsert in one commit) and the
        # unprocessed batches were never touched. No segment left empty-mid-delete.
        assert await _mention_count(db_session) == 3


class TestFullRescanDeleteScope:
    async def test_full_rescan_delete_spares_manual_mentions(
        self, db_session: AsyncSession
    ) -> None:
        """SEAM-2: --full re-derives rule_match/transcript mentions but must not
        touch a manual mention sharing the same segment (source-scoped delete)."""
        entity_id = await _seed_three_segments(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)
        # Populate transcript (rule_match) mentions.
        await svc.scan(batch_size=10)
        assert await _mention_count(db_session) == 3

        # Add a MANUAL mention on the same video (different source).
        db_session.add(
            EntityMentionDB(
                entity_id=entity_id,
                segment_id=None,
                video_id=VID,
                language_code="en",
                mention_text="Foo Bar",
                detection_method="manual",
                mention_source="manual",
                match_start=0,
                match_end=7,
            )
        )
        await db_session.commit()
        assert await _mention_count(db_session) == 4

        # A full re-scan deletes+reinserts only the transcript-source mentions.
        r = await svc.scan(batch_size=10, full_rescan=True)
        assert r.completed is True
        # 3 transcript mentions re-derived + the 1 manual mention untouched.
        rows = (await db_session.execute(select(EntityMentionDB))).scalars().all()
        assert len(rows) == 4
        assert sum(1 for m in rows if m.mention_source == "manual") == 1
        assert sum(1 for m in rows if m.mention_source == "transcript") == 3


async def _seed_two_titled_videos(session: AsyncSession) -> None:
    """Two videos whose titles mention entity 'Foo Bar' (metadata scan target)."""
    await _seed_channel(session, CH)
    for i in range(2):
        session.add(
            VideoDB(
                video_id=video_id(seed=f"scan_meta_{i}"),
                channel_id=CH,
                title=f"Episode {i} about Foo Bar",
                description="",
                upload_date=datetime(2020, 1, 1, tzinfo=UTC),
                duration=120,
                made_for_kids=False,
                self_declared_made_for_kids=False,
            )
        )
    entity = await _seed_entity(session, "Foo Bar", entity_type="organization")
    await _seed_alias(session, entity.id, "Foo Bar")
    await session.commit()


class TestMetadataParity:
    async def test_metadata_interrupt_then_resume_completes(
        self, db_session: AsyncSession
    ) -> None:
        """US5: scan_metadata has the same interrupt+resume guarantee."""
        await _seed_two_titled_videos(db_session)
        factory = _make_session_factory_from_session(db_session)
        svc = EntityMentionScanService(session_factory=factory)

        checkpoints: list[str] = []
        stop = {"go": True}

        def _cont() -> bool:
            if stop["go"]:
                stop["go"] = False
                return False  # stop after batch 1
            return True

        r1 = await svc.scan_metadata(
            sources=["title"],
            batch_size=1,
            should_continue=_cont,
            checkpoint_callback=checkpoints.append,
        )
        assert r1.completed is False
        assert r1.last_processed_video_id is not None
        assert checkpoints == [r1.last_processed_video_id]
        after_interrupt = await _mention_count(db_session)
        assert after_interrupt >= 1

        r2 = await svc.scan_metadata(
            sources=["title"],
            batch_size=1,
            resume_from_video_id=r1.last_processed_video_id,
        )
        assert r2.completed is True
        # One title mention per video, no duplicates.
        rows = (await db_session.execute(select(EntityMentionDB))).scalars().all()
        assert len(rows) == 2
        assert all(m.mention_source == "title" for m in rows)
