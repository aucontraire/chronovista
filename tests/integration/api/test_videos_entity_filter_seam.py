"""Seam test: the /videos entity filter matches the association count (#260).

Against a real Postgres. The load-bearing invariant of Feature #260 is that
``GET /videos?entity_id=E`` returns the **same** videos ``get_association_counts``
counts — including videos associated with E only via a tag. Before #260 the
filter read mentions only and silently dropped tag-only videos, so the count and
the list disagreed (the #240 inconsistency surviving at the filter layer).

The integration database is never reset, so every assertion is keyed on the
entity this test seeds — never a global total (project integration-db
shared-state rule).

- **T007 (US1)**: for an entity with a mix of mention and tag-only associations
  (including an unavailable video), the ``include_unavailable=true`` result
  count equals ``get_association_counts([E])[E].total``, and the tag-only video
  is present. Mutation-verify: reverting ``build_entity_qualification_subquery``
  to mentions-only drops the tag-only video and this assertion fails.
- **T008 (US1 regression)**: ``min_evidence=transcript`` returns the pre-#260
  mentions-only set (the tag-only video is absent, FR-007); a request with no
  entity filter is unchanged (FR-009), asserted against an independent count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.enums import AvailabilityStatus
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.entity_association_orm_factory import (
    seed_alias_tag_association,
    seed_mention_association,
    seed_tag_only_association,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_PFX = "s260"


async def _seed_videos(
    factory: async_sessionmaker[AsyncSession],
    available: list[str],
    unavailable: list[str],
) -> None:
    channel_id = f"UC{_PFX}SeamChannel00000"[:24]
    async with factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="S260 Seam Channel"))
            await s.commit()
        for vid in available:
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"S260 {vid}",
                        upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                        duration=60,
                        availability_status=AvailabilityStatus.AVAILABLE.value,
                    )
                )
        for vid in unavailable:
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"S260 {vid}",
                        upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                        duration=60,
                        availability_status=AvailabilityStatus.UNAVAILABLE.value,
                    )
                )
        await s.commit()


class TestFilterMatchesAssociationCount:
    async def test_tag_only_video_present_and_count_matches(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Two mention videos, one tag-only video V (available), and one
        # tag-associated but UNAVAILABLE video U.
        m1 = f"{_PFX}mena001"[:20]
        m2 = f"{_PFX}menb002"[:20]
        v = f"{_PFX}tagonly03"[:20]
        u = f"{_PFX}tagunav04"[:20]
        decoy = f"{_PFX}decoy005"[:20]
        await _seed_videos(
            integration_session_factory, available=[m1, m2, v, decoy], unavailable=[u]
        )

        async with integration_session_factory() as s:
            entity = await seed_mention_association(s, video_ids=[m1, m2])
            await seed_tag_only_association(s, entity=entity, video_ids=[v, u])
            # A decoy entity tag-associated with `decoy` only, so `decoy` exists
            # but is NOT associated with our entity.
            await seed_tag_only_association(s, video_ids=[decoy])
        entity_id = entity.id

        async with integration_session_factory() as s:
            counts = await EntityMentionRepository().get_association_counts(
                s, [entity_id]
            )
        expected_total = counts[entity_id].total
        assert expected_total == 4  # {m1, m2, v, u}

        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(entity_id),
                "include_unavailable": "true",
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        returned = {row["video_id"] for row in body["data"]}

        # FR-002: the filter count equals the association count (same
        # include-unavailable basis) — the whole feature.
        assert body["pagination"]["total"] == expected_total
        # The tag-only video is present (pre-#260 it was dropped).
        assert v in returned
        assert returned == {m1, m2, v, u}
        assert decoy not in returned

    async def test_video_associated_by_both_mention_and_tag_counted_once(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A2 double-count guard: a video associated with the SAME entity via
        both a mention AND a tag appears **exactly once** (the ``UNION ALL`` +
        ``count(DISTINCT entity_id)`` collapses the duplicate arm), and its
        ``total_mentions`` counts the mention only — the tag arm weighs 0 and
        must not inflate the score.
        """
        both = f"{_PFX}both001"[:20]
        await _seed_videos(
            integration_session_factory, available=[both], unavailable=[]
        )

        async with integration_session_factory() as s:
            entity = await seed_mention_association(s, video_ids=[both])
            # Same entity, same video, now ALSO via a tag.
            await seed_tag_only_association(s, entity=entity, video_ids=[both])
        entity_id = entity.id

        async with integration_session_factory() as s:
            counts = await EntityMentionRepository().get_association_counts(
                s, [entity_id]
            )
        assert counts[entity_id].total == 1  # one distinct video

        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(entity_id),
                "include_unavailable": "true",
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        rows = [row for row in body["data"] if row["video_id"] == both]
        # Exactly once, not once-per-arm.
        assert len(rows) == 1
        assert body["pagination"]["total"] == 1
        # One mention → total_mentions 1; the tag added 0 (not 2).
        assert rows[0]["total_mentions"] == 1


class TestEvidenceScopeAndNoFilterRegression:
    async def test_transcript_scope_excludes_tag_only_video(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        m1 = f"{_PFX}rmen001"[:20]
        v = f"{_PFX}rtag002"[:20]
        await _seed_videos(
            integration_session_factory, available=[m1, v], unavailable=[]
        )

        async with integration_session_factory() as s:
            entity = await seed_mention_association(s, video_ids=[m1])
            await seed_tag_only_association(s, entity=entity, video_ids=[v])
        entity_id = entity.id

        # FR-007: at TRANSCRIPT scope, tags do not qualify — the pre-#260
        # mentions-only set.
        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(entity_id),
                "min_evidence": "transcript",
                "include_unavailable": "true",
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        returned = {row["video_id"] for row in r.json()["data"]}
        assert returned == {m1}
        assert v not in returned

    async def test_no_entity_filter_matches_independent_count(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # FR-009: a request with no entity filter is unaffected. Asserted
        # against an independent query, never a constant (shared-DB rule).
        async with integration_session_factory() as s:
            expected = (
                await s.execute(
                    select(func.count())
                    .select_from(VideoDB)
                    .where(
                        VideoDB.availability_status
                        == AvailabilityStatus.AVAILABLE.value
                    )
                )
            ).scalar() or 0

        r = await async_client.get("/api/v1/videos", params={"limit": 1})
        assert r.status_code == 200, r.text
        assert r.json()["pagination"]["total"] == expected


class TestExclusionSymmetryAndAndNarrowing:
    """T011 (US2, #260) — exclusion is tag-inclusive and symmetric; AND narrows.

    ``exclude_entity_id=G`` now removes videos associated with G via a **tag**
    (not just a mention), because the exclusion consumes the same
    ``_tag_inclusive_association_arms`` helper qualification does (FR-003). And a
    second required ``entity_id`` only ever narrows the set (SC-004) — it can
    never broaden it.
    """

    async def test_tag_only_exclusion_removes_the_video(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # E mention-associates two videos; G tag-only-associates one of them.
        va = f"{_PFX}exa001"[:20]
        vg = f"{_PFX}exg002"[:20]
        await _seed_videos(
            integration_session_factory, available=[va, vg], unavailable=[]
        )

        async with integration_session_factory() as s:
            e = await seed_mention_association(s, video_ids=[va, vg])
            g = await seed_tag_only_association(s, video_ids=[vg])
        e_id, g_id = e.id, g.id

        # Without exclusion, E's set includes vg.
        r = await async_client.get(
            "/api/v1/videos", params={"entity_id": str(e_id), "limit": 100}
        )
        assert r.status_code == 200, r.text
        assert {row["video_id"] for row in r.json()["data"]} == {va, vg}

        # Excluding G (which reaches vg only via a tag) removes vg — proof the
        # exclusion arm is tag-inclusive and symmetric with qualification.
        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(e_id),
                "exclude_entity_id": str(g_id),
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        returned = {row["video_id"] for row in r.json()["data"]}
        assert returned == {va}
        assert vg not in returned

    async def test_second_required_entity_only_narrows(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # E: {x, y}; F: {y, z}. E∩F == {y}, never broader than either arm.
        x = f"{_PFX}andx001"[:20]
        y = f"{_PFX}andy002"[:20]
        z = f"{_PFX}andz003"[:20]
        await _seed_videos(
            integration_session_factory, available=[x, y, z], unavailable=[]
        )

        async with integration_session_factory() as s:
            e = await seed_mention_association(s, video_ids=[x, y])
            f = await seed_mention_association(s, video_ids=[y, z])
        e_id, f_id = e.id, f.id

        async def _ids(**params: str) -> set[str]:
            r = await async_client.get(
                "/api/v1/videos", params={"limit": 100, **params}
            )
            assert r.status_code == 200, r.text
            return {row["video_id"] for row in r.json()["data"]}

        e_only = await _ids(entity_id=str(e_id))
        f_only = await _ids(entity_id=str(f_id))
        # httpx serialises a repeated param from a list.
        r = await async_client.get(
            "/api/v1/videos",
            params=[
                ("entity_id", str(e_id)),
                ("entity_id", str(f_id)),
                ("limit", "100"),
            ],
        )
        assert r.status_code == 200, r.text
        both = {row["video_id"] for row in r.json()["data"]}

        assert e_only == {x, y}
        assert f_only == {y, z}
        assert both == {y}
        # AND never broadens: the intersection is a subset of each single arm.
        assert both <= e_only
        assert both <= f_only


class TestExclusionOnlyRequests:
    """Polish coverage (#260) — exclusion works with **no** required entity.

    ``exclude_entity_id`` is applied whether or not an ``entity_id`` is present
    (the router adds ``video_id NOT IN (excluded)`` unconditionally, and the
    pagination total derives from that same query), so an exclude-only request
    removes exactly the excluded entities' associated videos — tag arm included
    — and leaves everything else. Assertions are keyed on an independent
    baseline count and the seeded entities' ``get_association_counts`` (never a
    global constant), per the shared-integration-DB rule. ``sort_by=relevance``
    is intentionally not used: a relevance sort with no ``entity_id`` is
    correctly rejected by an existing router guard.
    """

    async def test_multi_entity_exclusion_removes_union_not_intersection(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # G1 mention-associates one video; G2 tag-only-associates a *different*
        # video. The two association sets are disjoint, so an OR (union)
        # exclusion removes both, while an AND (intersection) exclusion would
        # remove neither — the discriminating case.
        vg1 = f"{_PFX}xorg1v01"[:20]
        vg2 = f"{_PFX}xorg2v02"[:20]
        await _seed_videos(
            integration_session_factory, available=[vg1, vg2], unavailable=[]
        )

        async with integration_session_factory() as s:
            g1 = await seed_mention_association(s, video_ids=[vg1])
            g2 = await seed_tag_only_association(s, video_ids=[vg2])
        g1_id, g2_id = g1.id, g2.id

        # Each freshly-created entity associates only its one seeded video.
        async with integration_session_factory() as s:
            counts = await EntityMentionRepository().get_association_counts(
                s, [g1_id, g2_id]
            )
        assert counts[g1_id].total == 1
        assert counts[g2_id].total == 1

        async def _total(**params: str) -> int:
            r = await async_client.get("/api/v1/videos", params={"limit": 1, **params})
            assert r.status_code == 200, r.text
            return int(r.json()["pagination"]["total"])

        baseline = await _total()
        excl_g1 = await _total(exclude_entity_id=str(g1_id))
        excl_g2 = await _total(exclude_entity_id=str(g2_id))

        # httpx serialises a repeated param from a list of pairs.
        r = await async_client.get(
            "/api/v1/videos",
            params=[
                ("exclude_entity_id", str(g1_id)),
                ("exclude_entity_id", str(g2_id)),
                ("limit", "1"),
            ],
        )
        assert r.status_code == 200, r.text
        excl_both = int(r.json()["pagination"]["total"])

        # Each single exclusion removes exactly its one video.
        assert baseline - excl_g1 == 1
        assert baseline - excl_g2 == 1
        # The multi-entity exclusion removes the UNION of both sets (2 videos),
        # not the intersection (which is empty and would remove 0). This is the
        # OR semantics of exclusion (FR-014).
        assert baseline - excl_both == 2
        assert baseline - excl_both == counts[g1_id].total + counts[g2_id].total

    async def test_exclude_only_removes_mention_and_tag_videos(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # G reaches one video via a mention and another via a tag only. An
        # exclude-only request (no entity_id) must drop BOTH — proving the
        # exclusion arm is tag-inclusive even with no required entity present.
        vm = f"{_PFX}exomen01"[:20]
        vt = f"{_PFX}exotag02"[:20]
        decoy = f"{_PFX}exodec03"[:20]
        await _seed_videos(
            integration_session_factory,
            available=[vm, vt, decoy],
            unavailable=[],
        )

        async with integration_session_factory() as s:
            g = await seed_mention_association(s, video_ids=[vm])
            await seed_tag_only_association(s, entity=g, video_ids=[vt])
            # A decoy entity unrelated to G, tag-associated with `decoy`.
            await seed_tag_only_association(s, video_ids=[decoy])
        g_id = g.id

        async with integration_session_factory() as s:
            counts = await EntityMentionRepository().get_association_counts(s, [g_id])
        # G's mention video + tag video = 2 distinct associations.
        assert counts[g_id].total == 2

        async def _total(**params: str) -> int:
            r = await async_client.get("/api/v1/videos", params={"limit": 1, **params})
            assert r.status_code == 200, r.text
            return int(r.json()["pagination"]["total"])

        baseline = await _total()
        excl = await _total(exclude_entity_id=str(g_id))

        # Exactly G's two videos are removed — the mention one AND the tag-only
        # one — and nothing else (the count identity proves no over-removal).
        assert baseline - excl == 2
        assert baseline - excl == counts[g_id].total


class TestAliasTagArmExecutes:
    """The **alias-tag** arm of ``_tag_inclusive_association_arms`` runs against a
    real Postgres — not just mock-compiled.

    The alias-tag arm is the ``text()`` ``unnest(:a, :b)`` selectable with
    ``.columns(entity_id=Uuid, video_id=String, mention_weight=Integer)``, injected
    as the third arm of the 3-way ``UNION ALL``. It fires when an entity's non-ASR
    ``EntityAlias`` normalises to a ``TagAlias.normalized_form`` whose ``raw_form``
    is a ``VideoTag`` on the video — a path DISTINCT from the canonical-tag arm
    (``CanonicalTag.entity_id``), which the existing ``seed_tag_only_association``
    exercises.

    In this fixture V is reachable **only** through the alias-tag path: E has no
    ``EntityMention`` (mention arm empty) and the owning ``CanonicalTag`` has
    ``entity_id = NULL`` (canonical-tag arm empty). So if the alias-tag arm were
    dropped from ``_tag_inclusive_association_arms``, V would not appear and every
    assertion below would fail — that is what makes this a real-DB execution test
    of that specific arm (and proves its ``.columns()`` typing / ``UNION ALL``
    alignment work at runtime, not only under compilation).
    """

    async def test_alias_tag_only_video_present_and_count_matches(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        v = f"{_PFX}atv001"[:20]
        decoy = f"{_PFX}atdec02"[:20]
        await _seed_videos(
            integration_session_factory, available=[v, decoy], unavailable=[]
        )

        async with integration_session_factory() as s:
            # E ↔ V ONLY via the alias-tag path (no mention, canonical_tag
            # entity_id is NULL).
            entity = await seed_alias_tag_association(s, video_ids=[v])
            # A decoy entity alias-tag-associated with `decoy` only, so `decoy`
            # exists but is NOT associated with E.
            await seed_alias_tag_association(s, video_ids=[decoy])
        entity_id = entity.id

        async with integration_session_factory() as s:
            counts = await EntityMentionRepository().get_association_counts(
                s, [entity_id]
            )
        expected_total = counts[entity_id].total
        # Reached solely through the alias-tag path.
        assert expected_total == 1
        assert counts[entity_id].by_source.tag == 1

        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(entity_id),
                "include_unavailable": "true",
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        returned = {row["video_id"] for row in body["data"]}

        # The alias-tag arm executed and aligned in the UNION ALL: V is present.
        assert v in returned
        # Parity holds through the alias-tag path (FR-002).
        assert body["pagination"]["total"] == expected_total
        assert returned == {v}
        assert decoy not in returned

    async def test_alias_tag_exclusion_removes_the_video(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # E mention-associates two videos; G reaches one of them ONLY via the
        # alias-tag path. Excluding G must drop that video — proof the exclusion
        # side consumes the same alias-tag arm.
        va = f"{_PFX}atexa01"[:20]
        vg = f"{_PFX}atexg02"[:20]
        await _seed_videos(
            integration_session_factory, available=[va, vg], unavailable=[]
        )

        async with integration_session_factory() as s:
            e = await seed_mention_association(s, video_ids=[va, vg])
            g = await seed_alias_tag_association(s, video_ids=[vg])
        e_id, g_id = e.id, g.id

        # Without exclusion, E's set includes vg.
        r = await async_client.get(
            "/api/v1/videos", params={"entity_id": str(e_id), "limit": 100}
        )
        assert r.status_code == 200, r.text
        assert {row["video_id"] for row in r.json()["data"]} == {va, vg}

        # Excluding G (which reaches vg only via the alias-tag arm) removes vg.
        r = await async_client.get(
            "/api/v1/videos",
            params={
                "entity_id": str(e_id),
                "exclude_entity_id": str(g_id),
                "limit": 100,
            },
        )
        assert r.status_code == 200, r.text
        returned = {row["video_id"] for row in r.json()["data"]}
        assert returned == {va}
        assert vg not in returned


class TestRelevanceOrdersTagOnlyLast:
    """A4 / T013 (US3, #260) — under ``sort_by=relevance``, tag-only videos
    (``total_mentions`` 0) sort **after** every mention-ranked video, and the
    order is deterministic across two identical requests (SC-005).
    """

    async def test_tag_only_video_sorts_after_mention_ranked(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        rich = f"{_PFX}relr001"[:20]  # 2 mentions
        poor = f"{_PFX}relp002"[:20]  # 1 mention
        tag = f"{_PFX}relt003"[:20]  # 0 mentions (tag only)
        await _seed_videos(
            integration_session_factory,
            available=[rich, poor, tag],
            unavailable=[],
        )

        async with integration_session_factory() as s:
            entity = await seed_mention_association(s, video_ids=[rich, poor])
            # A second mention on `rich` gives it the higher relevance score.
            await seed_mention_association(s, entity=entity, video_ids=[rich])
            await seed_tag_only_association(s, entity=entity, video_ids=[tag])
        entity_id = entity.id

        async def _ordered() -> tuple[list[str], dict[str, int]]:
            r = await async_client.get(
                "/api/v1/videos",
                params={
                    "entity_id": str(entity_id),
                    "sort_by": "relevance",
                    "limit": 100,
                },
            )
            assert r.status_code == 200, r.text
            data = r.json()["data"]
            return [row["video_id"] for row in data], {
                row["video_id"]: row["total_mentions"] for row in data
            }

        order1, mentions = await _ordered()
        order2, _ = await _ordered()

        assert order1 == [rich, poor, tag]  # descending mention volume
        # Deterministic across identical requests (SC-005).
        assert order1 == order2
        # The tag-only video is last and scores 0.
        assert order1[-1] == tag
        assert mentions[tag] == 0
