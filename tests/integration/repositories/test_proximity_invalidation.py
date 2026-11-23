"""The single proximity invalidation operation (Feature 117, FR-010/FR-011).

``invalidate_proximity_scopes`` is the ONE way producers mark ``(video, language)``
scopes stale. These tests cross the real database: revision and failure-reset
semantics, the three scope-selection modes (one scope, every language of a video,
every scope an entity touches, including scopes reachable only through stored
records), argument validation, and the durability property that it writes inside
the caller's transaction without committing.

The incremental-equals-full equivalence test (SC-003) lands here with Feature 117
T027, once scope processing exists.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityPairProximity as EntityPairProximityDB
from chronovista.db.models import ProximityScopeState as ProximityScopeStateDB
from chronovista.repositories.entity_pair_proximity_repository import (
    EntityPairProximityRepository,
)
from tests.factories.proximity_seed import (
    canonical,
    seed_entity,
    seed_mention,
    seed_scope_state,
    seed_segment,
    seed_video,
)

pytestmark = pytest.mark.asyncio


def _vid(tag: str) -> str:
    return f"inv117{tag}{uuid.uuid4().hex[:8]}"


async def _states(
    session: AsyncSession, video_id: str
) -> dict[str, ProximityScopeStateDB]:
    rows = await session.execute(
        select(ProximityScopeStateDB)
        .where(ProximityScopeStateDB.video_id == video_id)
        .execution_options(populate_existing=True)
    )
    return {row.language_code: row for row in rows.scalars().all()}


class TestRevisionSemantics:
    async def test_first_invalidation_inserts_revision_one(
        self, db_session: AsyncSession
    ) -> None:
        video_id = _vid("a")
        await seed_video(db_session, video_id)

        touched = await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, video_id=video_id, language_code="en", reason="scan"
        )

        assert touched == 1
        state = (await _states(db_session, video_id))["en"]
        assert state.revision == 1
        assert state.computed_revision is None  # not computed yet
        assert state.reason == "scan"

    async def test_reinvalidation_bumps_revision_and_resets_failures(
        self, db_session: AsyncSession
    ) -> None:
        video_id = _vid("b")
        await seed_video(db_session, video_id)
        await seed_scope_state(
            db_session,
            video_id=video_id,
            language_code="en",
            state="failing",
            attempts=4,
        )

        await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, video_id=video_id, language_code="en", reason="correction"
        )

        state = (await _states(db_session, video_id))["en"]
        assert state.revision == 3  # seeded at 2, bumped once
        assert state.attempts == 0
        assert state.failed_rule_version is None
        assert state.next_attempt_at is None
        assert state.last_error is None
        assert state.reason == "correction"


class TestScopeSelection:
    async def test_video_alone_covers_every_transcript_language(
        self, db_session: AsyncSession
    ) -> None:
        video_id = _vid("c")
        await seed_video(db_session, video_id, ("en", "fr", "es"))

        touched = await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, video_id=video_id, reason="exclusion"
        )

        assert touched == 3
        assert set(await _states(db_session, video_id)) == {"en", "fr", "es"}

    async def test_entity_covers_mention_scopes_and_record_only_scopes(
        self, db_session: AsyncSession
    ) -> None:
        """Entity mode is mentions UNION stored records (research R8).

        ``mentioned`` holds a positioned mention of the entity. ``evidence_only``
        holds no mention any more, only a stale record that references the entity
        (as after its last mention was removed). Both must be invalidated, and a
        video the entity never touched must not be.
        """
        entity = await seed_entity(db_session)
        partner = await seed_entity(db_session)
        mentioned, evidence_only, untouched = _vid("m"), _vid("r"), _vid("u")
        for video_id in (mentioned, evidence_only, untouched):
            await seed_video(db_session, video_id)
        segment = await seed_segment(db_session, mentioned, "en", 10.0, 0)
        await seed_mention(
            db_session,
            entity_id=entity,
            video_id=mentioned,
            language_code="en",
            segment_id=segment,
        )
        seg_a = await seed_segment(db_session, evidence_only, "en", 10.0, 0)
        seg_b = await seed_segment(db_session, evidence_only, "en", 12.0, 1)
        a, b = canonical(entity, partner)
        db_session.add(
            EntityPairProximityDB(
                entity_a_id=a,
                entity_b_id=b,
                video_id=evidence_only,
                language_code="en",
                segment_a_id=seg_a,
                segment_b_id=seg_b,
                gap_seconds=2.0,
            )
        )
        await db_session.flush()

        touched = await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, entity_id=entity, reason="alias"
        )

        assert touched == 2
        assert "en" in await _states(db_session, mentioned)
        assert "en" in await _states(db_session, evidence_only)
        assert await _states(db_session, untouched) == {}


class TestArguments:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"video_id": "v", "entity_id": uuid.uuid4()},
            {"language_code": "en", "entity_id": uuid.uuid4()},
        ],
    )
    async def test_rejects_ambiguous_or_missing_selectors(
        self, db_session: AsyncSession, kwargs: dict[str, object]
    ) -> None:
        with pytest.raises(ValueError):
            await EntityPairProximityRepository().invalidate_proximity_scopes(
                db_session, reason="scan", **kwargs  # type: ignore[arg-type]
            )


class TestDurability:
    async def test_writes_in_the_callers_transaction_without_committing(
        self, db_session: AsyncSession
    ) -> None:
        """FR-010: the invalidation shares the caller's fate.

        It is visible inside the caller's transaction, and a rollback of that
        transaction (a producer whose change fails) discards it too, so an
        invalidation can never outlive a change that did not commit.
        """
        video_id = _vid("d")
        await seed_video(db_session, video_id)
        await db_session.commit()

        await EntityPairProximityRepository().invalidate_proximity_scopes(
            db_session, video_id=video_id, language_code="en", reason="scan"
        )
        assert "en" in await _states(db_session, video_id)

        await db_session.rollback()
        assert await _states(db_session, video_id) == {}
