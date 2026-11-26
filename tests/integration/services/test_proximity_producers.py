"""Behavioural tests for every transcript-proximity PRODUCER (Feature 117).

A *producer* is any code path that changes which positioned transcript mentions
qualify as proximity evidence. Each must call
``EntityPairProximityRepository.invalidate_proximity_scopes`` in the same transaction
as its change (FR-010/FR-011). A producer that forgets leaves a scope marked CURRENT
over stale records, and no unit test of the producer or of the computer can see that:
the defect lives in the seam between them.

Every test therefore has the same shape and crosses that seam from the outside:

1. Seed a video whose scope is CURRENT (and note whether the pair has a record).
2. Run the producer through its REAL entry point: the scan service, the batch
   correction service, the curation service, the HTTP router (``ASGITransport``),
   or the Typer command (``CliRunner``).
3. Assert the scope is no longer current (its ``revision`` advanced).
4. Recompute through the real ``process_stale_scopes`` and assert the scope is
   current again AND the pair's record appeared or disappeared as the producer
   implies.

Mutation results for each producer are recorded in the Feature 117 report; the
``Mutation`` line in each docstring names the call whose removal turns the test red.

Narrowest-function notes (stated rather than silently substituted):

- CLI commands call ``asyncio.run`` internally, which cannot nest inside the running
  test loop. ``invoke_cli`` runs the REAL Typer command (argument parsing included)
  with ``asyncio.run`` captured, then awaits the command's real ``_run`` coroutine on
  the test loop against the test session. Only the loop plumbing is replaced.
- Whitespace backfill: its own invalidation is shadowed by the re-scan's invalidation
  whenever the re-scan finds or deletes mentions, so the test that isolates it makes
  the re-scan fail (the case the invalidation exists for: normalization committed,
  offsets shifted, re-scan never completed).

Everything is synthetic: nonsense placeholder names, generated video ids.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.api.deps import get_db
from chronovista.api.main import app
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import EntityOperationLog as EntityOperationLogDB
from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.models.entity_operation_log import (
    AssociationExclusionRollback,
    EntityOperationLogCreate,
)
from chronovista.models.enums import (
    CorrectionType,
    DownloadReason,
    EntityType,
    TranscriptType,
)
from chronovista.models.video_transcript import VideoTranscriptCreate
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.entity_operation_log_repository import (
    EntityOperationLogRepository,
)
from chronovista.repositories.entity_video_exclusion_repository import (
    EntityVideoExclusionRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.tag_alias_repository import TagAliasRepository
from chronovista.repositories.tag_operation_log_repository import (
    TagOperationLogRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.entity_curation_service import EntityCurationService
from chronovista.services.entity_mention_scan_service import EntityMentionScanService
from chronovista.services.tag_management import TagManagementService
from chronovista.services.transcript_whitespace_service import (
    TranscriptWhitespaceBackfillService,
)
from tests.factories.mention_world import (
    A_NAME,
    B_NAME,
    GARBLE,
    World,
    add_alias,
    batch_service,
    invoke_cli,
    is_current,
    new_batch_id,
    recompute,
    scope_state,
    seed_world,
    session_factory,
    settle,
)
from tests.factories.proximity_seed import (
    canonical,
    seed_segment,
)

pytestmark = pytest.mark.asyncio

ACTOR = "test:producer"


# ---------------------------------------------------------------------------
# Seeding and observation helpers
# ---------------------------------------------------------------------------


async def _revisions(world: World, session: AsyncSession) -> dict[str, int]:
    return {
        language: (await scope_state(session, world.video_id, language)).revision
        for language in world.languages
    }


async def _records(
    session: AsyncSession, world: World, language: str | None = None
) -> list[EntityPairProximityDB]:
    a_id, b_id = canonical(world.a, world.b)
    stmt = select(EntityPairProximityDB).where(
        EntityPairProximityDB.entity_a_id == a_id,
        EntityPairProximityDB.entity_b_id == b_id,
    )
    if language is not None:
        stmt = stmt.where(EntityPairProximityDB.language_code == language)
    return list(
        (
            await session.execute(stmt.execution_options(populate_existing=True))
        ).scalars()
    )


async def _assert_invalidated(
    session: AsyncSession, world: World, before: dict[str, int]
) -> None:
    """Every language's scope advanced its revision and is no longer current."""
    for language in world.languages:
        state = await scope_state(session, world.video_id, language)
        assert state.revision > before[language], (
            f"{language}: revision did not advance ({before[language]} -> "
            f"{state.revision}); the producer did not invalidate this scope"
        )
        assert not is_current(state), f"{language}: scope still reports CURRENT"


async def _assert_recomputed(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    await recompute(session, monkeypatch, world)
    for language in world.languages:
        assert is_current(await scope_state(session, world.video_id, language))


def _curation_service() -> EntityCurationService:
    return EntityCurationService(
        named_entity_repo=NamedEntityRepository(),
        operation_log_repo=EntityOperationLogRepository(),
        entity_alias_repo=EntityAliasRepository(),
        entity_mention_repo=EntityMentionRepository(),
        entity_video_exclusion_repo=EntityVideoExclusionRepository(),
    )


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """The real FastAPI app over ASGI, with ``get_db`` bound to the test session."""

    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        with patch("chronovista.api.deps.youtube_oauth") as oauth:
            oauth.is_authenticated.return_value = True
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. Transcript scan (per-segment path and cross-segment path)
# ---------------------------------------------------------------------------


class TestScanProducer:
    async def test_per_segment_scan_that_writes_a_mention_adds_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scan writing A's first qualifying mention puts A near B.

        Entry point: ``EntityMentionScanService.scan`` (per-segment path).
        Mutation: remove the batch-scope ``invalidate_proximity_scopes`` loop.
        """
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text=f"we heard {A_NAME} speak",
            b_segment_text=f"then {B_NAME} replied",
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == [], "A has no mention yet"
        before = await _revisions(world, db_session)

        result = await EntityMentionScanService(
            session_factory=session_factory(db_session)
        ).scan(video_ids=[world.video_id], entity_ids=[world.a])

        assert result.mentions_found == 1, "scan must have written A's mention"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        (record,) = await _records(db_session, world)
        assert record.gap_seconds == 4.0

    async def test_cross_segment_scan_that_writes_a_mention_adds_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A name split over a segment boundary is found by the span pass.

        Entry point: ``EntityMentionScanService.scan`` (cross-segment path). The name
        is whole in no single segment, so the per-segment path writes nothing and the
        only possible invalidation is the cross-segment one.
        Mutation: remove the ``if mentions or delete_affected ...`` invalidation.
        """
        first, second = A_NAME.split(" ")
        world = await seed_world(
            db_session,
            a_mentioned=False,
            a_segment_text=f"the guest is {first}",
            b_segment_text=f"{second} is speaking",
        )
        # B's mention lives in a third segment close to the span's anchor.
        seg_b_far = await seed_segment(db_session, world.video_id, "en", 16.0, 2)
        await db_session.execute(
            update(TranscriptSegmentDB)
            .where(TranscriptSegmentDB.id == seg_b_far)
            .values(text=f"then {B_NAME} replied")
        )
        await db_session.execute(
            update(EntityMentionDB)
            .where(EntityMentionDB.entity_id == world.b)
            .values(segment_id=seg_b_far)
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []
        before = await _revisions(world, db_session)

        result = await EntityMentionScanService(
            session_factory=session_factory(db_session)
        ).scan(video_ids=[world.video_id], entity_ids=[world.a])

        assert result.mentions_found == 1, "scan must have written the spanning mention"
        spanning = (
            (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == world.a,
                        EntityMentionDB.end_segment_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(spanning) == 1, "the mention must have come from the span pass"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1


# ---------------------------------------------------------------------------
# 2. apply_to_segments with an entity, and its negative twin
# ---------------------------------------------------------------------------


async def _seed_garbled_world(session: AsyncSession) -> World:
    return await seed_world(
        session,
        a_mentioned=False,
        a_segment_text=f"we saw {GARBLE} here",
        b_segment_text=f"then {B_NAME} replied",
    )


class TestBatchCorrectionProducers:
    async def test_apply_to_segments_with_entity_adds_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An entity-aware correction creates a ``user_correction`` mention.

        Entry point: ``BatchCorrectionService.apply_to_segments(entity_id=...)``.
        Mutation: remove the ``invalidate_proximity_scopes`` loop in Step 5.
        """
        world = await _seed_garbled_world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []
        before = await _revisions(world, db_session)

        result = await batch_service().apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=A_NAME,
            segment_ids=[world.seg_a["en"]],
            correction_type=CorrectionType.PROPER_NOUN,
            auto_rebuild=False,
            entity_id=world.a,
            batch_id=new_batch_id(),
        )

        assert result.total_applied == 1
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1

    async def test_cross_segment_correction_invalidates_in_the_chunk_commit(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FR-010 atomicity on the boundary-spanning path (whole-branch review).

        ``_apply_cross_segment_corrections`` commits its mentions per chunk, BEFORE
        ``apply_to_segments`` reaches its own Step 5 invalidation. A failure in that
        window (here: the counter update right after the helper) must not leave the
        committed mentions in a scope still marked current.
        Mutation: remove the per-chunk invalidation in the helper.
        """
        world = await seed_world(
            db_session,
            a_mentioned=False,
            # Both tokens must differ from the name ("Zeta Quux"), or the correction
            # leaves segment A unchanged and no spanning mention is created.
            a_segment_text="we saw Zita",
            b_segment_text=f"Quuks then {B_NAME} replied",
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        before = await _revisions(world, db_session)

        async def fails(*_: object, **__: object) -> None:
            raise RuntimeError("failure after the chunk commit")

        monkeypatch.setattr(EntityMentionRepository, "update_entity_counters", fails)
        with pytest.raises(RuntimeError, match="after the chunk commit"):
            await batch_service().apply_to_segments(
                db_session,
                pattern="Zita Quuks",
                replacement=A_NAME,
                segment_ids=[world.seg_a["en"]],
                correction_type=CorrectionType.PROPER_NOUN,
                auto_rebuild=False,
                entity_id=world.a,
                batch_id=new_batch_id(),
                cross_segment=True,
            )
        await db_session.rollback()
        monkeypatch.undo()

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1

    async def test_text_only_correction_leaves_the_scope_current(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NEGATIVE: a correction with no entity creates no mention, so nothing is stale.

        The correction really is applied (so the producer ran); the scope must stay
        CURRENT at the same revision, or every text fix would force a recompute.
        """
        world = await _seed_garbled_world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        before = await _revisions(world, db_session)

        result = await batch_service().apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=A_NAME,
            segment_ids=[world.seg_a["en"]],
            correction_type=CorrectionType.PROPER_NOUN,
            auto_rebuild=False,
            entity_id=None,
        )

        assert result.total_applied == 1, "the text correction must have been applied"
        segment = (
            await db_session.execute(
                select(TranscriptSegmentDB)
                .where(TranscriptSegmentDB.id == world.seg_a["en"])
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert segment.has_correction is True
        assert await _revisions(world, db_session) == before
        assert is_current(await scope_state(db_session, world.video_id))

    async def test_correction_that_replaces_a_mentions_text_drops_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#426: a text-only correction that removes the entity from its words drops it.

        Entry point: ``TranscriptCorrectionService.apply_correction`` (via
        ``apply_to_segments``), whose rebase step moves, re-points or removes the
        segment's mentions. A's only mention is a name-exempt ``asr_match`` on the
        garbled form; the correction replaces it with words that are not A, so the
        mention is removed (fixing it to A's name would re-point it instead).
        Mutation: remove the rebase step's ``invalidate_proximity_scopes`` call.
        """
        world = await seed_world(
            db_session,
            a_mention_text=GARBLE,
            a_detection="asr_match",
            a_segment_text=f"we saw {GARBLE} here",
            b_segment_text=f"then {B_NAME} replied",
            a_match_start=len("we saw "),
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        result = await batch_service().apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement="somebody else",
            segment_ids=[world.seg_a["en"]],
            correction_type=CorrectionType.PROPER_NOUN,
            auto_rebuild=False,
            entity_id=None,
            batch_id=new_batch_id(),
        )

        assert result.total_applied == 1
        remaining = (
            await db_session.execute(
                select(EntityMentionDB.id).where(EntityMentionDB.entity_id == world.a)
            )
        ).all()
        assert remaining == [], "A is no longer said there, so its mention must be gone"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_batch_revert_by_batch_id_removes_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reverting a batch deletes its correction-created mentions.

        Entry point: ``BatchCorrectionService.batch_revert(batch_id=...)``.
        Mutation: remove the invalidation loop in the batch_id branch.
        """
        world = await _seed_garbled_world(db_session)
        await db_session.commit()
        batch_id = new_batch_id()
        service = batch_service()
        await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=A_NAME,
            segment_ids=[world.seg_a["en"]],
            auto_rebuild=False,
            entity_id=world.a,
            batch_id=batch_id,
        )
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1, "precondition: A is near B"
        before = await _revisions(world, db_session)

        await service.batch_revert(db_session, batch_id=batch_id)

        assert (
            not (
                await db_session.execute(
                    select(EntityMentionDB).where(
                        EntityMentionDB.entity_id == world.a,
                        EntityMentionDB.correction_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        ), "revert must have deleted the correction-created mention"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_batch_revert_by_pattern_removes_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same as above through the pattern-mode branch.

        Entry point: ``BatchCorrectionService.batch_revert(pattern=...)``.
        Mutation: remove the invalidation loop in the pattern-mode branch.
        """
        world = await _seed_garbled_world(db_session)
        await db_session.commit()
        service = batch_service()
        await service.apply_to_segments(
            db_session,
            pattern=GARBLE,
            replacement=A_NAME,
            segment_ids=[world.seg_a["en"]],
            auto_rebuild=False,
            entity_id=world.a,
            batch_id=new_batch_id(),
        )
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        await service.batch_revert(
            db_session, pattern=A_NAME, video_ids=[world.video_id]
        )

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []


# ---------------------------------------------------------------------------
# 3. Entity-video exclusion endpoints (every language of the video)
# ---------------------------------------------------------------------------


class TestExclusionEndpoints:
    async def test_exclude_endpoint_drops_the_record_in_every_language(
        self,
        api: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Exclusion has no language column, so BOTH languages must be invalidated.

        Entry point: ``POST /api/v1/entities/{id}/excluded-videos``.
        Mutation: remove the ``invalidate_proximity_scopes`` call in the exclude route.
        """
        world = await seed_world(db_session, languages=("en", "fr"))
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1
        before = await _revisions(world, db_session)

        response = await api.post(
            f"/api/v1/entities/{world.a}/excluded-videos",
            json={"video_id": world.video_id},
        )

        assert response.status_code == 200, response.text
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_restore_endpoint_brings_the_record_back_in_every_language(
        self,
        api: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Entry point: ``DELETE /api/v1/entities/{id}/excluded-videos/{video}``.

        Mutation: remove the ``invalidate_proximity_scopes`` call in the restore route.
        """
        world = await seed_world(db_session, languages=("en", "fr"))
        await db_session.commit()
        exclude = await api.post(
            f"/api/v1/entities/{world.a}/excluded-videos",
            json={"video_id": world.video_id},
        )
        assert exclude.status_code == 200, exclude.text
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == [], "precondition: A is excluded"
        before = await _revisions(world, db_session)

        response = await api.delete(
            f"/api/v1/entities/{world.a}/excluded-videos/{world.video_id}"
        )

        assert response.status_code == 204, response.text
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1


# ---------------------------------------------------------------------------
# 4. Transcript (re)download
# ---------------------------------------------------------------------------


class TestTranscriptRedownload:
    async def test_recreating_segments_invalidates_the_scope(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-downloading deletes and recreates the segments its mentions anchor on.

        The mentions and records cascade away with the old segments, but the scope
        state does not: without an invalidation it would stay CURRENT over a transcript
        that no longer matches what was measured.

        Entry point: ``VideoTranscriptRepository.create_or_update(raw_transcript_data=...)``.
        Mutation: remove the ``invalidate_proximity_scopes`` call in
        ``_create_segments_from_raw_data``.
        """
        world = await seed_world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        await VideoTranscriptRepository().create_or_update(
            db_session,
            VideoTranscriptCreate(
                video_id=world.video_id,
                language_code="en",
                transcript_text="replacement transcript",
                transcript_type=TranscriptType.MANUAL,
                download_reason=DownloadReason.USER_REQUEST,
            ),
            raw_transcript_data={
                "snippets": [{"text": "replacement", "start": 0.0, "duration": 2.0}],
                "source": "youtube_transcript_api",
            },
        )

        remaining = (
            (
                await db_session.execute(
                    select(TranscriptSegmentDB.text).where(
                        TranscriptSegmentDB.video_id == world.video_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert list(remaining) == ["replacement"], "segments must have been recreated"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []


# ---------------------------------------------------------------------------
# 5. Whitespace backfill
# ---------------------------------------------------------------------------


class _FailingScan:
    """Scan stand-in whose re-scan never completes (hard kill / crash case)."""

    async def scan(self, **_: Any) -> None:
        raise RuntimeError("re-scan interrupted")


class TestWhitespaceBackfill:
    async def _world(self, session: AsyncSession) -> World:
        return await seed_world(
            session,
            a_segment_text=f"the  guest {A_NAME}  speaks",
            b_segment_text=f"then {B_NAME} replied",
        )

    async def test_normalization_commits_its_invalidation_even_if_the_rescan_fails(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Normalization shifts offsets; the scope must be stale even if no re-scan ran.

        Entry point: ``TranscriptWhitespaceBackfillService.run(apply=True)`` with a
        re-scan that raises. This isolates the service's own invalidation, which a
        successful re-scan would otherwise shadow with its own.
        Mutation: remove the ``invalidate_proximity_scopes`` call in ``_process_video``.
        """
        world = await self._world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        before = await _revisions(world, db_session)

        summary = await TranscriptWhitespaceBackfillService(
            session_factory(db_session),
            scan_service=cast(EntityMentionScanService, _FailingScan()),
        ).run(apply=True, video_id=world.video_id)

        assert summary.videos_failed == 1, "the re-scan was supposed to fail"
        text = (
            await db_session.execute(
                select(TranscriptSegmentDB.text).where(
                    TranscriptSegmentDB.id == world.seg_a["en"]
                )
            )
        ).scalar_one()
        assert text == f"the guest {A_NAME} speaks", "normalization must have committed"
        await _assert_invalidated(db_session, world, before)

    async def test_normalization_with_a_real_rescan_converges_to_the_same_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End to end with the real re-scan: scope stale, then current with the record.

        The re-scan also invalidates, so this test is NOT mutation-sensitive to the
        whitespace service's own call (the failing-rescan test above is); it guards the
        composed behaviour.
        """
        world = await self._world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        await TranscriptWhitespaceBackfillService(
            session_factory(db_session),
            scan_service=EntityMentionScanService(
                session_factory=session_factory(db_session)
            ),
        ).run(apply=True, video_id=world.video_id)

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1


# ---------------------------------------------------------------------------
# 6. Entity curation service
# ---------------------------------------------------------------------------

NICK = "Zeta Nick"


async def _seed_alias_world(session: AsyncSession) -> tuple[World, EntityAliasDB]:
    """A's only qualifying mention is under an alias (not its canonical name)."""
    world = await seed_world(session, a_mention_text=NICK)
    alias_id = await add_alias(session, world.a, NICK)
    alias = (
        await session.execute(select(EntityAliasDB).where(EntityAliasDB.id == alias_id))
    ).scalar_one()
    return world, alias


class TestCurationServiceProducers:
    async def test_delete_alias_removes_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deleting an alias deletes its auto-detected mentions.

        Entry point: ``EntityCurationService.delete_alias``.
        Mutation: remove the entity-wide ``invalidate_proximity_scopes`` call in ``delete_alias``.
        """
        world, alias = await _seed_alias_world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        entity = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == world.a)
            )
        ).scalar_one()
        before = await _revisions(world, db_session)

        removed, _op = await _curation_service().delete_alias(
            db_session, entity=entity, alias=alias, actor=ACTOR
        )

        assert removed == 1
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_delete_alias_also_disqualifies_a_kept_correction_mention(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ``user_correction`` mention is KEPT by ``delete_alias``, but when its
        text matched only the deleted alias it stops qualifying (it is not
        name-exempt), so its scope must still be invalidated (Phase 5 contract
        review). Mutation: invalidate only the deleted mentions' scopes.
        """
        world = await seed_world(
            db_session, a_mention_text=NICK, a_detection="user_correction"
        )
        alias_id = await add_alias(db_session, world.a, NICK)
        alias = (
            await db_session.execute(
                select(EntityAliasDB).where(EntityAliasDB.id == alias_id)
            )
        ).scalar_one()
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        entity = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == world.a)
            )
        ).scalar_one()
        before = await _revisions(world, db_session)

        removed, _op = await _curation_service().delete_alias(
            db_session, entity=entity, alias=alias, actor=ACTOR
        )

        assert removed == 0  # the correction mention is kept
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_undo_alias_delete_restores_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Undoing the deletion restores the alias and its mentions.

        Entry point: ``EntityCurationService.undo_operation`` on an ``alias_delete`` op.
        Mutation: remove the entity-wide ``invalidate_proximity_scopes`` call in
        ``_undo_alias_delete``.
        """
        world, alias = await _seed_alias_world(db_session)
        await db_session.commit()
        service = _curation_service()
        entity = (
            await db_session.execute(
                select(NamedEntityDB).where(NamedEntityDB.id == world.a)
            )
        ).scalar_one()
        _removed, op_id = await service.delete_alias(
            db_session, entity=entity, alias=alias, actor=ACTOR
        )
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == [], "precondition: alias deleted"
        before = await _revisions(world, db_session)

        await service.undo_operation(db_session, op_id, actor=ACTOR)

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1

    async def test_rename_removes_the_record_and_undo_restores_it(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The canonical name is a visible name; renaming un-qualifies old-name mentions.

        Entry points: ``update_entity(canonical_name=...)`` then ``undo_operation`` on
        the resulting ``update`` op.
        Mutations: remove the invalidation in ``update_entity``; separately, remove the
        one in the ``update`` branch of ``undo_operation``.
        """
        world = await seed_world(db_session, a_alias=False)
        await db_session.commit()
        service = _curation_service()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        await service.update_entity(
            db_session, world.a, canonical_name="Wexford Plinth", actor=ACTOR
        )

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert (
            await _records(db_session, world) == []
        ), "old-name mention stops qualifying"

        op = (
            await db_session.execute(
                select(EntityOperationLogDB).where(
                    EntityOperationLogDB.entity_id == world.a,
                    EntityOperationLogDB.operation_type == "update",
                )
            )
        ).scalar_one()
        before_undo = await _revisions(world, db_session)

        await service.undo_operation(db_session, op.id, actor=ACTOR)

        await _assert_invalidated(db_session, world, before_undo)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert (
            len(await _records(db_session, world)) == 1
        ), "restored name qualifies again"

    @pytest.mark.parametrize("undo_of", ["association_exclude", "association_restore"])
    async def test_undoing_an_association_exclusion_flips_the_record(
        self,
        undo_of: str,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both branches of ``_undo_association_exclusion`` change an F091 exclusion.

        Undo of ``association_exclude`` removes the exclusion (record appears); undo of
        ``association_restore`` re-adds it (record disappears).
        Entry point: ``EntityCurationService.undo_operation``.
        Mutation: remove the single ``invalidate_proximity_scopes`` call (both red).
        """
        world = await seed_world(db_session, languages=("en", "fr"))
        exclusion_repo = EntityVideoExclusionRepository()
        if undo_of == "association_exclude":
            await exclusion_repo.add(
                db_session, world.a, world.video_id, excluded_by=ACTOR
            )
        op = await EntityOperationLogRepository().create(
            db_session,
            obj_in=EntityOperationLogCreate(
                entity_id=world.a,
                operation_type=undo_of,
                rollback_data=AssociationExclusionRollback(video_id=world.video_id),
                performed_by=ACTOR,
            ),
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        expected_before = 0 if undo_of == "association_exclude" else 1
        for language in world.languages:
            assert (
                len(await _records(db_session, world, language)) == expected_before
            ), "precondition"
        before = await _revisions(world, db_session)

        await _curation_service().undo_operation(db_session, op.id, actor=ACTOR)

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert (
                len(await _records(db_session, world, language)) == 1 - expected_before
            )


# ---------------------------------------------------------------------------
# 7. Alias endpoints (every language of the entity's mentions)
# ---------------------------------------------------------------------------


class TestAliasEndpoints:
    async def test_create_alias_endpoint_makes_the_mention_qualify(
        self,
        api: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A new alias is a new visible name; entity-scoped invalidation hits en AND fr.

        Entry point: ``POST /api/v1/entities/{id}/aliases``.
        Mutation: remove the ``invalidate_proximity_scopes`` call in ``create_entity_alias``.
        """
        world = await seed_world(
            db_session, languages=("en", "fr"), a_mention_text=NICK
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == [], "NICK is not a name yet"
        before = await _revisions(world, db_session)

        response = await api.post(
            f"/api/v1/entities/{world.a}/aliases", json={"alias_name": NICK}
        )

        assert response.status_code == 201, response.text
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1

    async def test_rename_alias_endpoint_makes_the_mention_qualify(
        self,
        api: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Renaming an alias to the mention's text makes it a visible name.

        Entry point: ``PATCH /api/v1/entities/{id}/aliases/{alias_id}``.
        Mutation: remove the ``invalidate_proximity_scopes`` call in ``update_entity_alias``.
        """
        world = await seed_world(
            db_session, languages=("en", "fr"), a_mention_text=NICK
        )
        alias_id = await add_alias(db_session, world.a, "Zeta Nik")
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []
        before = await _revisions(world, db_session)

        response = await api.patch(
            f"/api/v1/entities/{world.a}/aliases/{alias_id}",
            json={"alias_name": NICK},
        )

        assert response.status_code == 200, response.text
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1


# ---------------------------------------------------------------------------
# 8. CLI alias commands
# ---------------------------------------------------------------------------


class TestCliAliasCommands:
    async def test_add_alias_command_makes_the_mention_qualify(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Entry point: ``chronovista entities add-alias``.

        Mutation: remove the ``invalidate_proximity_scopes`` call in ``add_alias``.
        """
        world = await seed_world(
            db_session, languages=("en", "fr"), a_mention_text=NICK
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []
        before = await _revisions(world, db_session)

        await invoke_cli(
            monkeypatch, db_session, ["add-alias", A_NAME, "--alias", NICK]
        )

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1

    async def test_remove_alias_command_keeps_the_mention_but_drops_the_record(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mention REMAINS but its text stops being a visible name.

        Entry point: ``chronovista entities remove-alias``.
        Mutation: remove the ``invalidate_proximity_scopes`` call in ``remove_alias``.
        """
        world, _alias = await _seed_alias_world(db_session)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1
        before = await _revisions(world, db_session)

        await invoke_cli(
            monkeypatch, db_session, ["remove-alias", A_NAME, "--alias", NICK]
        )

        kept = (
            (
                await db_session.execute(
                    select(EntityMentionDB).where(EntityMentionDB.entity_id == world.a)
                )
            )
            .scalars()
            .all()
        )
        assert len(kept) == 1, "remove-alias must leave the mention in place"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []

    async def test_edit_alias_rename_command_makes_the_mention_qualify(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Entry point: ``chronovista entities edit-alias --new-name``.

        Mutation: remove the ``invalidate_proximity_scopes`` call in ``edit_alias``.
        """
        world = await seed_world(
            db_session, languages=("en", "fr"), a_mention_text=NICK
        )
        await add_alias(db_session, world.a, "Zeta Nik")
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == []
        before = await _revisions(world, db_session)

        await invoke_cli(
            monkeypatch,
            db_session,
            ["edit-alias", A_NAME, "--alias", "Zeta Nik", "--new-name", NICK],
        )

        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        for language in world.languages:
            assert len(await _records(db_session, world, language)) == 1


# ---------------------------------------------------------------------------
# 9. Tag classification linking to an existing entity
# ---------------------------------------------------------------------------


class TestTagClassifyLink:
    async def test_linking_a_tag_to_an_existing_entity_adds_a_visible_name(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Classify links the tag by NORMALIZED name and adds its display name as alias.

        The entity's canonical name differs from the tag's display name only by a double
        space, which normalization collapses but the visible-name fold does not. So the
        mention "Zeta Quux" qualifies only once classify adds that display name as an
        alias. This is a narrow case (a normalization-equal but fold-different name);
        it is the only way this producer changes evidence in practice.

        Entry point: ``TagManagementService.classify``.
        Mutation: remove the ``invalidate_proximity_scopes`` call after the alias create.
        """
        world = await seed_world(
            db_session,
            a_name="Zeta  Quux",
            a_alias=False,
            a_mention_text="Zeta Quux",
        )
        db_session.add(
            CanonicalTagDB(
                canonical_form="Zeta Quux",
                normalized_form="zeta quux",
                alias_count=1,
                video_count=0,
                status="active",
            )
        )
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        assert await _records(db_session, world) == [], "double-space name != mention"
        before = await _revisions(world, db_session)

        result = await TagManagementService(
            canonical_tag_repo=CanonicalTagRepository(),
            tag_alias_repo=TagAliasRepository(),
            named_entity_repo=NamedEntityRepository(),
            entity_alias_repo=EntityAliasRepository(),
            operation_log_repo=TagOperationLogRepository(),
        ).classify(db_session, "zeta quux", EntityType.PERSON, actor=ACTOR)

        assert result is not None
        aliases = (
            (
                await db_session.execute(
                    select(EntityAliasDB.alias_name).where(
                        EntityAliasDB.entity_id == world.a
                    )
                )
            )
            .scalars()
            .all()
        )
        assert list(aliases) == ["Zeta Quux"], "classify must have linked and aliased"
        await _assert_invalidated(db_session, world, before)
        await _assert_recomputed(db_session, monkeypatch, world)
        assert len(await _records(db_session, world)) == 1


# ---------------------------------------------------------------------------
# 10. Atomicity (FR-010)
# ---------------------------------------------------------------------------


class TestAtomicity:
    async def test_rolled_back_producer_persists_neither_change_nor_invalidation(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A producer's change and its invalidation commit or vanish together.

        Runs the real ``update_entity`` (rename plus invalidation), then rolls the
        transaction back. A second connection observes the committed state: while the
        transaction is open it must see neither half (the invalidation never commits on
        its own), and after the rollback it must still see neither.
        """
        world = await seed_world(db_session, a_alias=False)
        await db_session.commit()
        await settle(db_session, monkeypatch, world)
        await db_session.commit()
        before = await _revisions(world, db_session)
        observer_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

        async def observe() -> tuple[int, str]:
            async with observer_factory() as observer:
                revision = (await scope_state(observer, world.video_id)).revision
                name = (
                    await observer.execute(
                        select(NamedEntityDB.canonical_name).where(
                            NamedEntityDB.id == world.a
                        )
                    )
                ).scalar_one()
                return revision, name

        await _curation_service().update_entity(
            db_session, world.a, canonical_name="Wexford Plinth", actor=ACTOR
        )
        in_txn_revision = (await scope_state(db_session, world.video_id)).revision
        assert (
            in_txn_revision > before["en"]
        ), "inside the transaction it is invalidated"
        assert await observe() == (before["en"], A_NAME), "no autonomous commit"

        await db_session.rollback()

        assert await observe() == (before["en"], A_NAME)
        state = await scope_state(db_session, world.video_id)
        assert state.revision == before["en"]
        assert is_current(state), "a rolled-back change must leave the scope CURRENT"
