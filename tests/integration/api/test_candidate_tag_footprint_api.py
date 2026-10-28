"""Cross-Feature contract test 2 for Feature 097 US4: tag footprint + tag link.

Real database, real HTTP through the app (``ASGITransport`` via ``async_client``).
The footprint endpoints compute a delta (tag videos minus already-associated
videos) and ``POST /entities/{id}/tag-link`` mutates ``canonical_tags.entity_id``.
The load-bearing claims crossed here:

- **SC-008 no double-count**: a video already associated through the derived
  alias-tag arm is not counted as "newly associated", and after the link the
  entity's ``/videos`` list contains every tag video exactly once.
- **Re-assignment refused**: linking a tag already held by entity A to entity B
  is refused (409) with ownership unchanged — moving a tag between entities is
  out of scope (the only re-classify primitive is destructive).
- **Pre-approval preview**: a candidate (no entity yet) is measured against the
  derived-arm baseline for its label.

The integration DB is shared and never reset, so every value is a unique
synthetic string (letters only, so ``TagNormalizationService`` leaves it
unchanged) and every seeded row is purged on teardown.
"""

from __future__ import annotations

import random
import string
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import CandidateSuggestion as CandidateDB
from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import Channel as ChannelDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTag as VideoTagDB
from chronovista.models.enums import AvailabilityStatus
from tests.factories.entity_association_orm_factory import (
    CanonicalTagDBFactory,
    EntityAliasDBFactory,
    TagAliasDBFactory,
    VideoTagDBFactory,
)
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _letters(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class _World:
    """Seeds rows for one test and remembers them for teardown."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.channel_id = f"UC97fp{_letters(18)}"[:24]
        self.video_ids: list[str] = []
        self.tag_ids: list[uuid.UUID] = []
        self.entity_ids: list[uuid.UUID] = []
        self.candidate_ids: list[uuid.UUID] = []
        self.raw_forms: list[str] = []

    async def video(self) -> str:
        vid = f"97fp{_letters(14)}"
        async with self.factory() as s:
            if await s.get(ChannelDB, self.channel_id) is None:
                s.add(ChannelDB(channel_id=self.channel_id, title="Fp97 Channel"))
                await s.flush()
            s.add(
                VideoDB(
                    video_id=vid,
                    channel_id=self.channel_id,
                    title=f"Fp97 {vid}",
                    # Old date: never crowds /videos page 1 in the shared DB.
                    upload_date=datetime(2009, 1, 1, tzinfo=UTC),
                    duration=60,
                    availability_status=AvailabilityStatus.AVAILABLE.value,
                )
            )
            await s.commit()
        self.video_ids.append(vid)
        return vid

    async def tag(
        self,
        normalized: str,
        aliases: list[tuple[str, str, str]],
        *,
        owner: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Seed an active canonical tag.

        ``aliases`` is ``(raw_form, alias_normalized_form, video_id)`` — one
        tag alias per entry, tagged onto its video.
        """
        async with self.factory() as s:
            tag = CanonicalTagDBFactory.build(
                canonical_form=normalized,
                normalized_form=normalized,
                entity_id=owner,
                # Unclassified unless owned: classify() refuses a tag that
                # already carries an entity_type (without force).
                entity_type="organization" if owner is not None else None,
                alias_count=len(aliases),
                video_count=len(aliases),
            )
            s.add(tag)
            await s.flush()
            for order, (raw, alias_norm, vid) in enumerate(aliases):
                s.add(
                    TagAliasDBFactory.build(
                        raw_form=raw,
                        normalized_form=alias_norm,
                        canonical_tag_id=tag.id,
                    )
                )
                s.add(VideoTagDBFactory.build(video_id=vid, tag=raw, tag_order=order))
                self.raw_forms.append(raw)
            await s.commit()
            self.tag_ids.append(tag.id)
            return tag.id

    async def entity(self, name: str, *, with_name_alias: bool) -> uuid.UUID:
        """Seed an active entity; the name alias feeds the alias-tag arm."""
        eid = _new_uuid()
        async with self.factory() as s:
            s.add(
                create_named_entity_db(
                    id=eid,
                    canonical_name=name,
                    canonical_name_normalized=name,
                    entity_type="organization",
                    status="active",
                )
            )
            await s.flush()
            if with_name_alias:
                s.add(
                    EntityAliasDBFactory.build(
                        entity_id=eid,
                        alias_name=name,
                        alias_name_normalized=name,
                        alias_type="name_variant",
                    )
                )
            await s.commit()
        self.entity_ids.append(eid)
        return eid

    async def candidate(self, label: str) -> uuid.UUID:
        row = CandidateDB(
            source_channel="relation",
            wikidata_qid="Q97016" + "".join(random.choices(string.digits, k=9)),
            label=label,
            label_normalized=label,
            type_hint="organization",
            token_count=len(label.split()),
            corroboration_count=1,
            dangling_edge_count=1,
            salience=0,
            score=0.0,
            triage="grounds_nowhere",
            provenance={"seed_entity_ids": [str(_new_uuid())], "relations": ["x"]},
            review_status="pending",
        )
        async with self.factory() as s:
            s.add(row)
            await s.commit()
        self.candidate_ids.append(row.id)
        return row.id

    async def tag_owner(self, tag_id: uuid.UUID) -> uuid.UUID | None:
        async with self.factory() as s:
            return (
                await s.execute(
                    select(CanonicalTagDB.entity_id).where(CanonicalTagDB.id == tag_id)
                )
            ).scalar_one()

    async def purge(self) -> None:
        async with self.factory() as s:
            await s.execute(
                delete(TagOperationLogDB).where(
                    TagOperationLogDB.target_canonical_id.in_(self.tag_ids)
                )
            )
            await s.execute(
                delete(CandidateDB).where(CandidateDB.id.in_(self.candidate_ids))
            )
            # Detach tags from entities before deleting either side.
            for tag_id in self.tag_ids:
                tag = await s.get(CanonicalTagDB, tag_id)
                if tag is not None:
                    tag.entity_id = None
            await s.flush()
            await s.execute(
                delete(VideoTagDB).where(VideoTagDB.video_id.in_(self.video_ids))
            )
            await s.execute(
                delete(TagAliasDB).where(TagAliasDB.canonical_tag_id.in_(self.tag_ids))
            )
            await s.execute(
                delete(CanonicalTagDB).where(CanonicalTagDB.id.in_(self.tag_ids))
            )
            await s.execute(
                delete(EntityAliasDB).where(
                    EntityAliasDB.entity_id.in_(self.entity_ids)
                )
            )
            await s.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id.in_(self.entity_ids))
            )
            await s.execute(delete(VideoDB).where(VideoDB.video_id.in_(self.video_ids)))
            await s.execute(
                delete(ChannelDB).where(ChannelDB.channel_id == self.channel_id)
            )
            await s.commit()


@pytest.fixture
async def world(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[_World, None]:
    w = _World(integration_session_factory)
    yield w
    await w.purge()


async def _entity_video_ids(client: AsyncClient, entity_id: uuid.UUID) -> list[str]:
    """Every video id the /videos entity filter returns (with duplicates kept)."""
    r = await client.get(
        "/api/v1/videos",
        params={"entity_id": str(entity_id), "limit": 100},
    )
    assert r.status_code == 200, r.text
    return [row["video_id"] for row in r.json()["data"]]


class TestLinkBecomesAssociationWithoutDoubleCount:
    async def test_link_adds_only_variant_video_and_never_duplicates(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        name = f"fpa {_letters(10)} authority"
        variant_raw = f"{name} variant raw"
        variant_norm = f"{_letters(8)} variant form"
        v_name = await world.video()
        v_variant = await world.video()
        tag_id = await world.tag(
            name,
            [(name, name, v_name), (variant_raw, variant_norm, v_variant)],
        )
        entity_id = await world.entity(name, with_name_alias=True)

        # Baseline: the derived alias-tag arm already associates the name video
        # and ONLY that one.
        assert await _entity_video_ids(async_client, entity_id) == [v_name]

        before = await async_client.get(f"/api/v1/entities/{entity_id}/tag-footprint")
        assert before.status_code == 200, before.text
        matches = before.json()["matches"]
        assert len(matches) == 1
        assert matches[0]["normalized_form"] == name
        # Tag covers {v_name, v_variant}; entity already has {v_name} -> 1 new.
        assert matches[0]["would_newly_associate"] == 1
        assert matches[0]["owned_by_entity_id"] is None

        link = await async_client.post(
            f"/api/v1/entities/{entity_id}/tag-link",
            json={"normalized_form": name, "entity_type": "organization"},
        )
        assert link.status_code == 200, link.text
        assert link.json() == {
            "normalized_form": name,
            "linked_entity_id": str(entity_id),
        }
        # Seam proof: the FK really moved, not just the response body.
        assert await world.tag_owner(tag_id) == entity_id

        after_ids = await _entity_video_ids(async_client, entity_id)
        # Both videos, each exactly once: v_name is reachable via the alias-tag
        # arm AND the new canonical-tag arm, yet must not appear twice.
        assert sorted(after_ids) == sorted([v_name, v_variant])
        assert len(after_ids) == len(set(after_ids))

        again = await async_client.get(f"/api/v1/entities/{entity_id}/tag-footprint")
        assert again.status_code == 200, again.text
        assert again.json()["matches"][0]["would_newly_associate"] == 0
        assert again.json()["matches"][0]["owned_by_entity_id"] == str(entity_id)


class TestRelinkIsRefused:
    async def test_relink_of_owned_tag_is_refused_and_ownership_unchanged(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        """Re-assignment is deferred (F097): a tag owned by another entity is
        refused 409, with ownership and both entities' associations unchanged —
        the destructive force-delete re-classify path is never reached."""
        name = f"fpb {_letters(10)} guild"
        v1 = await world.video()
        v2 = await world.video()
        # Entities carry NO name alias so only the canonical-tag arm is in play.
        entity_a = await world.entity(f"fpb a {_letters(10)}", with_name_alias=False)
        entity_b = await world.entity(f"fpb b {_letters(10)}", with_name_alias=False)
        tag_id = await world.tag(
            name, [(name, name, v1), (f"{name} raw", f"{name} raw", v2)], owner=entity_a
        )

        assert sorted(await _entity_video_ids(async_client, entity_a)) == sorted(
            [v1, v2]
        )
        assert await _entity_video_ids(async_client, entity_b) == []

        link = await async_client.post(
            f"/api/v1/entities/{entity_b}/tag-link",
            json={"normalized_form": name, "entity_type": "organization"},
        )
        assert link.status_code == 409, link.text

        # Ownership and associations are untouched — entity A was not deleted.
        assert await world.tag_owner(tag_id) == entity_a
        assert sorted(await _entity_video_ids(async_client, entity_a)) == sorted(
            [v1, v2]
        )
        assert await _entity_video_ids(async_client, entity_b) == []

    async def test_footprint_reports_current_owner_before_relink(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        name = f"fpc {_letters(10)} union"
        v1 = await world.video()
        entity_a = await world.entity(f"fpc a {_letters(10)}", with_name_alias=False)
        entity_b = await world.entity(name, with_name_alias=False)
        await world.tag(name, [(name, name, v1)], owner=entity_a)

        r = await async_client.get(f"/api/v1/entities/{entity_b}/tag-footprint")
        assert r.status_code == 200, r.text
        match = r.json()["matches"][0]
        assert match["owned_by_entity_id"] == str(entity_a)
        assert match["would_newly_associate"] == 1


class TestCandidatePreApprovalPreview:
    async def test_candidate_delta_is_measured_against_derived_arm_baseline(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        label = f"fpd {_letters(10)} society"
        v_name = await world.video()
        v_variant = await world.video()
        await world.tag(
            label,
            [
                (label, label, v_name),
                (f"{label} raw", f"{_letters(9)} other", v_variant),
            ],
        )
        candidate_id = await world.candidate(label)

        r = await async_client.get(f"/api/v1/candidates/{candidate_id}/tag-footprint")
        assert r.status_code == 200, r.text
        matches = r.json()["matches"]
        assert len(matches) == 1
        assert matches[0]["normalized_form"] == label
        # Tag covers 2 videos; name-matched baseline covers 1 -> 1 newly claimed.
        assert matches[0]["would_newly_associate"] == 1

    async def test_candidate_without_matching_tag_has_no_matches(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        candidate_id = await world.candidate(f"fpe {_letters(12)} nomatch")

        r = await async_client.get(f"/api/v1/candidates/{candidate_id}/tag-footprint")
        assert r.status_code == 200, r.text
        assert r.json() == {"matches": []}

    async def test_unknown_candidate_is_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"/api/v1/candidates/{uuid.uuid4()}/tag-footprint")
        assert r.status_code == 404, r.text


class TestTagLinkErrors:
    async def test_missing_entity_is_404(self, async_client: AsyncClient) -> None:
        r = await async_client.post(
            f"/api/v1/entities/{uuid.uuid4()}/tag-link",
            json={"normalized_form": "fpf nothing", "entity_type": "organization"},
        )
        assert r.status_code == 404, r.text

    async def test_invalid_entity_type_is_400(
        self, async_client: AsyncClient, world: _World
    ) -> None:
        name = f"fpg {_letters(10)} bad type"
        entity_id = await world.entity(name, with_name_alias=False)
        r = await async_client.post(
            f"/api/v1/entities/{entity_id}/tag-link",
            json={"normalized_form": name, "entity_type": "not_a_real_type"},
        )
        assert r.status_code == 400, r.text

    async def test_missing_entity_footprint_is_404(
        self, async_client: AsyncClient
    ) -> None:
        r = await async_client.get(f"/api/v1/entities/{uuid.uuid4()}/tag-footprint")
        assert r.status_code == 404, r.text
