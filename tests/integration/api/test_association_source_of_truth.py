"""Cross-view data-contract integration tests for Feature 080.

These assert the invariants the "one source of truth" feature exists to hold,
through a real database and the real endpoints (Constitution: Cross-Feature Data
Contract Verification):

- **INV-1 (#321/FR-024b):** the co-occurrence "appears with" count for a partner
  equals the ``/videos`` two-entity intersection ``pagination.total`` for the
  same pair, under the same evidence scope AND the same availability setting —
  including a pair that co-occurs only via a **tag**, which the pre-080
  mentions-only panel undercounted or hid.
- **INV-2 (#252/FR-004):** an entity's association count honours availability, so
  it equals the default (available-only) video-list total and never exceeds it.
- **INV-3 (FR-005):** a pair sharing a video ONLY via a tag still co-occurs — the
  behavioural guard that the co-occurrence path uses the shared association rule
  and no raw ``entity_mentions``-only path survives.

All fixtures use the shared association factory helpers and per-run unique video
ids (the integration DB is never reset), with neutral placeholder content only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.repositories.entity_mention_repository import EntityMentionRepository
from tests.factories.entity_association_orm_factory import (
    seed_channel_with_videos,
    seed_mention_association,
    seed_tag_only_association,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Without this, async tests are silently skipped under coverage.
pytestmark = pytest.mark.asyncio

_CH = ("UCf080assoc" + "0" * 24)[:24]
# Every id this module seeds carries this prefix, so cleanup can purge exactly
# its own rows from the shared, never-reset integration DB (and not pollute the
# global-count assertions in sibling suites — canonical tags, categories).
_PFX = "f080"
_ENTITY_NORM_PREFIX = "f080 "


async def _purge(session: AsyncSession) -> None:
    """Delete every row this module seeds, FK-safe, by its id/name prefix."""
    ent_ids = (
        (
            await session.execute(
                select(NamedEntityDB.id).where(
                    NamedEntityDB.canonical_name_normalized.like(
                        f"{_ENTITY_NORM_PREFIX}%"
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if ent_ids:
        ct_ids = (
            (
                await session.execute(
                    select(CanonicalTagDB.id).where(
                        CanonicalTagDB.entity_id.in_(ent_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if ct_ids:
            await session.execute(
                delete(TagAliasDB).where(TagAliasDB.canonical_tag_id.in_(ct_ids))
            )
            await session.execute(
                delete(CanonicalTagDB).where(CanonicalTagDB.id.in_(ct_ids))
            )
        await session.execute(
            delete(EntityMentionDB).where(EntityMentionDB.entity_id.in_(ent_ids))
        )
        await session.execute(
            delete(EntityAliasDB).where(EntityAliasDB.entity_id.in_(ent_ids))
        )
        await session.execute(
            delete(NamedEntityDB).where(NamedEntityDB.id.in_(ent_ids))
        )
    await session.execute(
        delete(VideoTagDB).where(VideoTagDB.video_id.like(f"{_PFX}%"))
    )
    await session.execute(
        delete(EntityMentionDB).where(EntityMentionDB.video_id.like(f"{_PFX}%"))
    )
    await session.execute(delete(VideoDB).where(VideoDB.video_id.like(f"{_PFX}%")))
    await session.execute(delete(ChannelDB).where(ChannelDB.channel_id == _CH))
    await session.commit()


@pytest.fixture(autouse=True)
async def _clean_shared_db(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    """Purge this module's seeded rows before and after each test.

    The integration DB is shared and never reset; this module seeds canonical
    tags, videos, and entities that would otherwise accumulate and skew the
    global-count assertions in sibling API suites. Scoping cleanup to the
    ``f080`` prefix keeps those suites unaffected.
    """
    async with integration_session_factory() as session:
        await _purge(session)
    yield
    async with integration_session_factory() as session:
        await _purge(session)


def _ids() -> str:
    """A random, per-run-unique suffix so each test seeds fresh videos/entities.

    The co-occurrence panel ranks EVERY entity sharing the subject's videos, so
    reusing video ids across runs on the never-reset integration DB would let a
    previous run's entity surface as a spurious partner. ``uuid4`` (not ``uuid7``,
    whose leading hex is a slow-moving timestamp that collides within ~65 s) gives
    real per-run randomness, keeping each subject's partner set to exactly the
    entities this run seeded and entity names clear of the unique-name constraint.
    """
    return uuid.uuid4().hex[:12]


def _shared_count(panel: dict[str, Any], partner_id: uuid.UUID) -> int | None:
    """The partner's ``shared_video_count`` in a co-occurrence response, or None."""
    for row in panel["data"]:
        if row["entity_id"] == str(partner_id):
            return int(row["shared_video_count"])
    return None


async def _intersection_total(
    client: AsyncClient,
    a: uuid.UUID,
    b: uuid.UUID,
    *,
    min_evidence: str = "any",
    include_unavailable: bool = False,
) -> int:
    params: dict[str, Any] = {
        "entity_id": [str(a), str(b)],
        "min_evidence": min_evidence,
        "limit": 100,
    }
    if include_unavailable:
        params["include_unavailable"] = "true"
    r = await client.get("/api/v1/videos", params=params)
    assert r.status_code == 200, r.text
    return int(r.json()["pagination"]["total"])


async def _panel(
    client: AsyncClient,
    subject: uuid.UUID,
    *,
    min_evidence: str = "any",
    include_unavailable: bool = False,
) -> dict[str, Any]:
    # 50 == MAX_COOCCURRING_LIMIT; the fixtures seed at most a couple of partners.
    params: dict[str, Any] = {"min_evidence": min_evidence, "limit": 50}
    if include_unavailable:
        params["include_unavailable"] = "true"
    r = await client.get(f"/api/v1/entities/{subject}/co-occurring", params=params)
    assert r.status_code == 200, r.text
    return r.json()


class TestCooccurrenceMatchesIntersection:
    """INV-1 (#321/FR-024b): panel count == intersection total, under same basis."""

    async def test_tag_only_pair_counts_match_across_scopes_and_availability(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sfx = _ids()
        vm = f"f080vm{sfx}"[:20]  # A & B share via MENTION (available)
        vt = f"f080vt{sfx}"[:20]  # A & B share via TAG ONLY (available)
        vu = f"f080vu{sfx}"[:20]  # A & B share via TAG (UNAVAILABLE)
        vc = f"f080vc{sfx}"[:20]  # A & C share via MENTION (available) -- common case

        async with integration_session_factory() as s:
            await seed_channel_with_videos(
                s, channel_id=_CH, available=[vm, vt, vc], unavailable=[vu]
            )
        async with integration_session_factory() as s:
            a = await seed_mention_association(
                s, video_ids=[vm, vc], entity_name=f"f080 subject {sfx}"
            )
            b = await seed_mention_association(
                s, video_ids=[vm], entity_name=f"f080 partner b {sfx}"
            )
            c = await seed_mention_association(
                s, video_ids=[vc], entity_name=f"f080 partner c {sfx}"
            )
            await seed_tag_only_association(s, entity=a, video_ids=[vt, vu])
            await seed_tag_only_association(s, entity=b, video_ids=[vt, vu])

        # ANY scope, available-only (default): A&B share {vm (mention), vt (tag)} = 2.
        # Pre-080 the mentions-only panel would have shown 1 and diverged.
        panel_any = await _panel(async_client, a.id)
        assert _shared_count(panel_any, b.id) == 2
        assert _shared_count(panel_any, b.id) == await _intersection_total(
            async_client, a.id, b.id
        )

        # Common case (mention-only pair A&C) is unchanged: {vc} = 1 (SC-004).
        assert _shared_count(panel_any, c.id) == 1
        assert _shared_count(panel_any, c.id) == await _intersection_total(
            async_client, a.id, c.id
        )

        # TRANSCRIPT scope: tags drop, A&B share {vm} = 1.
        panel_tx = await _panel(async_client, a.id, min_evidence="transcript")
        assert _shared_count(panel_tx, b.id) == 1
        assert _shared_count(panel_tx, b.id) == await _intersection_total(
            async_client, a.id, b.id, min_evidence="transcript"
        )

        # include_unavailable: A&B share {vm, vt, vu} = 3 (FR-011 parity under toggle).
        panel_all = await _panel(async_client, a.id, include_unavailable=True)
        assert _shared_count(panel_all, b.id) == 3
        assert _shared_count(panel_all, b.id) == await _intersection_total(
            async_client, a.id, b.id, include_unavailable=True
        )


class TestAssociationCountsHonourAvailability:
    """INV-2 (#252/FR-004): count == default available-only list; never exceeds it."""

    async def test_count_excludes_unavailable_by_default(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sfx = _ids()
        va = f"f080ea{sfx}"[:20]  # available mention video
        vu = f"f080eu{sfx}"[:20]  # UNAVAILABLE mention video

        async with integration_session_factory() as s:
            await seed_channel_with_videos(
                s, channel_id=_CH, available=[va], unavailable=[vu]
            )
        async with integration_session_factory() as s:
            e = await seed_mention_association(
                s, video_ids=[va, vu], entity_name=f"f080 counted {sfx}"
            )

        async with integration_session_factory() as s:
            repo = EntityMentionRepository()
            default_counts = await repo.get_association_counts(s, [e.id])
            all_counts = await repo.get_association_counts(
                s, [e.id], include_unavailable=True
            )

        # Default is available-only: {va} = 1, strictly fewer than the all basis.
        assert default_counts[e.id].total == 1
        assert all_counts[e.id].total == 2
        assert default_counts[e.id].total < all_counts[e.id].total
        # The per-source breakdown is available-only too.
        assert default_counts[e.id].by_source.transcript == 1

        # The detail header count equals the default (available-only) video list.
        detail = await async_client.get(f"/api/v1/entities/{e.id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["video_count"] == 1

        list_default = await async_client.get(
            "/api/v1/videos", params={"entity_id": str(e.id), "limit": 100}
        )
        assert list_default.status_code == 200, list_default.text
        assert list_default.json()["pagination"]["total"] == 1

        # And when the caller opts in, the detail count matches the all basis.
        detail_all = await async_client.get(
            f"/api/v1/entities/{e.id}", params={"include_unavailable": "true"}
        )
        assert detail_all.status_code == 200, detail_all.text
        assert detail_all.json()["data"]["video_count"] == 2

        # Same-page consistency (Feature 080): the entity detail page's EMBEDDED
        # video list (/entities/{id}/videos) must agree with the header count on
        # the same page — default available-only, and the toggle reveals the rest.
        embedded_default = await async_client.get(f"/api/v1/entities/{e.id}/videos")
        assert embedded_default.status_code == 200, embedded_default.text
        assert embedded_default.json()["pagination"]["total"] == 1  # == header

        embedded_all = await async_client.get(
            f"/api/v1/entities/{e.id}/videos", params={"include_unavailable": "true"}
        )
        assert embedded_all.status_code == 200, embedded_all.text
        assert embedded_all.json()["pagination"]["total"] == 2


class TestSingleDefinitionGuard:
    """INV-3 (FR-005): a tag-only shared pair still co-occurs (no raw path left)."""

    async def test_tag_only_shared_pair_is_visible_in_panel(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        sfx = _ids()
        vt = f"f080gt{sfx}"[:20]  # shared ONLY via tag; neither entity has a mention

        async with integration_session_factory() as s:
            await seed_channel_with_videos(s, channel_id=_CH, available=[vt])
        async with integration_session_factory() as s:
            p = await seed_tag_only_association(
                s, video_ids=[vt], entity_name=f"f080 guard p {sfx}"
            )
            q = await seed_tag_only_association(
                s, video_ids=[vt], entity_name=f"f080 guard q {sfx}"
            )

        # Pre-080 (raw mentions-only path) P has zero mentions, so its subject
        # video set would be empty and Q would be invisible. The shared rule
        # includes the tag arm, so Q appears with shared_video_count == 1.
        panel = await _panel(async_client, p.id)
        assert _shared_count(panel, q.id) == 1
        assert _shared_count(panel, q.id) == await _intersection_total(
            async_client, p.id, q.id
        )
