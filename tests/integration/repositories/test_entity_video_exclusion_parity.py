"""Cross-surface parity test for the Feature 091 manual-association exclusion.

The constitution's Cross-Feature Data Contract mandate (and spec FR-004) require that an
excluded ``(entity, video)`` pair disappears from EVERY association surface in lockstep —
never from some while others still show or count it. A mock-SQL test of the arms-union
sites cannot see this: four readers build associations with different shapes
(``get_entity_video_list``, ``get_association_counts``, the qualification filter, and the
video-side ``get_video_entity_associations``). This real-DB test seeds a derived
(tag-only, no stored mention) association, excludes one pair, and asserts the removal is
reflected identically across all four — the test that catches the bypass.

Uses the ``db_session`` fixture (create_all + drop_all per test), so no cleanup needed.
Name-free placeholders only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityVideoExclusion as EntityVideoExclusionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from chronovista.repositories.entity_video_exclusion_repository import (
    EntityVideoExclusionRepository,
)
from tests.factories.entity_association_orm_factory import (
    seed_channel_with_videos,
    seed_mention_association,
    seed_tag_only_association,
)

pytestmark = pytest.mark.asyncio

_CH = ("UCf091excl" + "0" * 24)[:24]


def _as_uuid(value: Any) -> uuid.UUID:
    """Normalise an entity id that a surface may return as UUID or str."""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class TestExclusionParityAcrossSurfaces:
    async def test_excluding_one_pair_is_reflected_on_every_surface(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v_excl = "f091xcl1"  # to be unlinked
        v_keep = "f091keep1"  # must survive untouched

        # Seed a DERIVED association: entity ↔ both videos via a tag only (no stored
        # EntityMention) — the hard case that has no row to delete.
        await seed_channel_with_videos(
            db_session, channel_id=_CH, available=[v_excl, v_keep]
        )
        entity = await seed_tag_only_association(
            db_session,
            video_ids=[v_excl, v_keep],
            entity_name="F091 subject",
        )
        eid = entity.id

        # BEFORE: both videos present on every surface.
        list_before, total_before = await repo.get_entity_video_list(
            db_session, eid, limit=50
        )
        counts_before = await repo.get_association_counts(db_session, [eid])
        qual_before = await repo.build_entity_qualification_subquery(db_session, [eid])
        filter_before = set(
            (await db_session.execute(select(qual_before.c.video_id))).scalars().all()
        )
        panel_before = await repo.get_video_entity_associations(db_session, v_excl)

        assert total_before == 2
        assert {r["video_id"] for r in list_before} == {v_excl, v_keep}
        assert counts_before[eid].total == 2
        assert filter_before == {v_excl, v_keep}
        assert eid in {uuid.UUID(r["entity_id"]) for r in panel_before}

        # EXCLUDE (eid, v_excl).
        created = await exclusions.add(db_session, eid, v_excl, excluded_by="test")
        await db_session.commit()
        assert created is True

        # AFTER: v_excl gone from every surface; v_keep untouched; counts −1.
        list_after, total_after = await repo.get_entity_video_list(
            db_session, eid, limit=50
        )
        counts_after = await repo.get_association_counts(db_session, [eid])
        qual_after = await repo.build_entity_qualification_subquery(db_session, [eid])
        filter_after = set(
            (await db_session.execute(select(qual_after.c.video_id))).scalars().all()
        )
        panel_after = await repo.get_video_entity_associations(db_session, v_excl)

        assert total_after == 1, "entity video list total must drop by exactly one"
        assert {r["video_id"] for r in list_after} == {v_keep}
        assert counts_after[eid].total == 1, "association count must drop in lockstep"
        assert filter_after == {v_keep}, "the /videos qualification filter must drop it"
        assert eid not in {
            uuid.UUID(r["entity_id"]) for r in panel_after
        }, "the video-side panel must drop the unlinked entity (symmetry)"

    async def test_undo_restores_the_derived_association(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091undo1"

        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        entity = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 undo"
        )
        eid = entity.id

        await exclusions.add(db_session, eid, v, excluded_by="test")
        await db_session.commit()
        _, total_excluded = await repo.get_entity_video_list(db_session, eid, limit=50)
        assert total_excluded == 0

        removed = await exclusions.remove(db_session, eid, v)
        await db_session.commit()
        assert removed is True
        restored, total_restored = await repo.get_entity_video_list(
            db_session, eid, limit=50
        )
        assert total_restored == 1
        assert {r["video_id"] for r in restored} == {v}


class TestExclusionMentionBearingParity:
    """T016(a): a MENTION-bearing excluded pair (not tag-only) must also drop
    everywhere — this exercises the video-panel ``summary_by_id`` path that the
    tag-only parity test never reaches."""

    async def test_excluding_a_mention_bearing_pair_drops_everywhere(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091men1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        entity = await seed_mention_association(
            db_session, video_ids=[v], entity_name="F091 mention subject"
        )
        eid = entity.id

        _, total_before = await repo.get_entity_video_list(db_session, eid, limit=50)
        counts_before = await repo.get_association_counts(db_session, [eid])
        panel_before = await repo.get_video_entity_associations(db_session, v)
        assert total_before == 1
        assert counts_before[eid].total == 1
        assert eid in {_as_uuid(r["entity_id"]) for r in panel_before}

        assert await exclusions.add(db_session, eid, v, excluded_by="test") is True
        await db_session.commit()

        list_after, total_after = await repo.get_entity_video_list(
            db_session, eid, limit=50
        )
        counts_after = await repo.get_association_counts(db_session, [eid])
        qual_after = await repo.build_entity_qualification_subquery(db_session, [eid])
        filter_after = set(
            (await db_session.execute(select(qual_after.c.video_id))).scalars().all()
        )
        panel_after = await repo.get_video_entity_associations(db_session, v)

        assert total_after == 0
        assert list_after == []
        assert eid not in counts_after or counts_after[eid].total == 0
        assert filter_after == set()
        assert eid not in {
            _as_uuid(r["entity_id"]) for r in panel_after
        }, "video panel must drop the unlinked mention-bearing entity"


class TestExclusionCooccurrence:
    """T016(b): an excluded pair must drop from 'appears with' co-occurrence on
    BOTH the subject side and the partner side."""

    async def test_excluding_shared_video_drops_cooccurrence_both_sides(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091co1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e1 = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 co subject one"
        )
        e2 = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 co subject two"
        )

        co1_before = await repo.get_cooccurring_entities(db_session, entity_id=e1.id)
        co2_before = await repo.get_cooccurring_entities(db_session, entity_id=e2.id)
        assert e2.id in {_as_uuid(r["entity_id"]) for r in co1_before}
        assert e1.id in {_as_uuid(r["entity_id"]) for r in co2_before}

        assert await exclusions.add(db_session, e1.id, v, excluded_by="test") is True
        await db_session.commit()

        co1_after = await repo.get_cooccurring_entities(db_session, entity_id=e1.id)
        co2_after = await repo.get_cooccurring_entities(db_session, entity_id=e2.id)
        assert e2.id not in {
            _as_uuid(r["entity_id"]) for r in co1_after
        }, "subject side: the excluded video is gone from e1's video set"
        assert e1.id not in {
            _as_uuid(r["entity_id"]) for r in co2_after
        }, "partner side: e1 is dropped as a partner of e2"


class TestExclusionEntityIsolation:
    """T017: excluding (E1, V) must leave (E2, V) intact on every surface."""

    async def test_excluding_one_entity_leaves_the_other(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091iso1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e1 = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 iso one"
        )
        e2 = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 iso two"
        )

        assert await exclusions.add(db_session, e1.id, v, excluded_by="test") is True
        await db_session.commit()

        _, t1 = await repo.get_entity_video_list(db_session, e1.id, limit=50)
        c1 = await repo.get_association_counts(db_session, [e1.id])
        list2, t2 = await repo.get_entity_video_list(db_session, e2.id, limit=50)
        c2 = await repo.get_association_counts(db_session, [e2.id])
        panel = await repo.get_video_entity_associations(db_session, v)
        panel_ids = {_as_uuid(r["entity_id"]) for r in panel}

        assert t1 == 0
        assert e1.id not in c1 or c1[e1.id].total == 0
        assert t2 == 1, "the untouched entity keeps the video"
        assert {r["video_id"] for r in list2} == {v}
        assert c2[e2.id].total == 1
        assert (
            e1.id not in panel_ids
        ), "excluded entity gone from the shared video panel"
        assert e2.id in panel_ids, "untouched entity still on the shared video panel"


class TestRestoreAfterBasisRemoved:
    """T022: if the only basis disappears while a pair is excluded, undo must
    leave the video absent (nothing qualifies it) with no error."""

    async def test_restore_does_not_reappear_when_basis_gone(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091bz1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 basis gone"
        )

        assert await exclusions.add(db_session, e.id, v, excluded_by="test") is True
        await db_session.commit()
        _, t_excluded = await repo.get_entity_video_list(db_session, e.id, limit=50)
        assert t_excluded == 0

        # Remove the pair's only basis (its tag), then undo the exclusion.
        await db_session.execute(delete(VideoTagDB).where(VideoTagDB.video_id == v))
        await db_session.commit()
        assert await exclusions.remove(db_session, e.id, v) is True
        await db_session.commit()

        _, t_restored = await repo.get_entity_video_list(db_session, e.id, limit=50)
        assert t_restored == 0, "no qualifying basis remains → stays absent, no error"


class TestExclusionCascadeAndZeroState:
    """T024: deleting an entity or video removes its exclusions (ON DELETE
    CASCADE); an entity with no exclusions behaves exactly as before."""

    async def test_deleting_entity_cascades_its_exclusions(
        self, db_session: AsyncSession
    ) -> None:
        exclusions = EntityVideoExclusionRepository()
        v = "f091cas1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 cascade entity"
        )
        await exclusions.add(db_session, e.id, v, excluded_by="test")
        await db_session.commit()
        assert await exclusions.exists(db_session, e.id, v) is True

        await db_session.execute(delete(NamedEntityDB).where(NamedEntityDB.id == e.id))
        await db_session.commit()
        remaining = (
            await db_session.execute(
                select(EntityVideoExclusionDB).where(
                    EntityVideoExclusionDB.entity_id == e.id
                )
            )
        ).all()
        assert remaining == [], "deleting the entity must cascade-delete its exclusions"

    async def test_deleting_video_cascades_its_exclusions(
        self, db_session: AsyncSession
    ) -> None:
        exclusions = EntityVideoExclusionRepository()
        v = "f091cas2"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 cascade video"
        )
        await exclusions.add(db_session, e.id, v, excluded_by="test")
        await db_session.commit()
        assert await exclusions.exists(db_session, e.id, v) is True

        # Drop the incidental tag scaffolding first (``video_tags`` FK is NOT
        # cascading, so it would block the delete) — this isolates the video to
        # the exclusion FK, which is what we're asserting cascades.
        await db_session.execute(delete(VideoTagDB).where(VideoTagDB.video_id == v))
        await db_session.commit()
        await db_session.execute(delete(VideoDB).where(VideoDB.video_id == v))
        await db_session.commit()
        remaining = (
            await db_session.execute(
                select(EntityVideoExclusionDB).where(
                    EntityVideoExclusionDB.video_id == v
                )
            )
        ).all()
        assert remaining == [], "deleting the video must cascade-delete its exclusions"

    async def test_zero_state_empty_list_and_unchanged(
        self, db_session: AsyncSession
    ) -> None:
        repo = EntityMentionRepository()
        exclusions = EntityVideoExclusionRepository()
        v = "f091zero1"
        await seed_channel_with_videos(db_session, channel_id=_CH, available=[v])
        e = await seed_tag_only_association(
            db_session, video_ids=[v], entity_name="F091 zero state"
        )
        page, total = await exclusions.list_for_entity(
            db_session, e.id, limit=50, offset=0
        )
        assert page == []
        assert total == 0
        _, vid_total = await repo.get_entity_video_list(db_session, e.id, limit=50)
        assert vid_total == 1, "with no exclusions the entity's videos are unchanged"
