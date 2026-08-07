"""Integration tests for POST /entities/{entity_id}/tags (Feature 064, US1/US2).

Every test here issues a **real HTTP request**. The router owns precondition
resolution and error mapping, and the service reports a missing entity and a
missing tag with the same ``ValueError("... not found")`` — so a service-level
test cannot see a 404 that names the wrong resource. This branch's own history
contains exactly that defect.

Fixtures purge before seeding: the integration database is never reset between
runs, so a run that fails before its cleanup leaves rows behind and the next
run fails on a unique constraint, which reads as a code failure.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from uuid_utils import uuid7

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import VideoTag as VideoTagDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

# Neutral, obviously-disposable names; the prefix means cleanup cannot match a
# real row.
PREFIX = "ect064"
ENTITY_NAME = "Ect064 Harbour Board"
ENTITY_NORM = "ect064 harbour board"
TAG_MAIN = f"{PREFIX} harbour board"
TAG_OTHER = f"{PREFIX} harbour brd"
TAG_THIRD = f"{PREFIX} the harbour board"


# ---------------------------------------------------------------------------
# Shared fixture (T010a)
# ---------------------------------------------------------------------------


async def _purge(factory: async_sessionmaker[AsyncSession]) -> None:
    """Remove everything this module creates, in FK-safe order."""
    async with factory() as s:
        await s.execute(
            CanonicalTagDB.__table__.update()
            .where(CanonicalTagDB.normalized_form.like(f"{PREFIX}%"))
            .values(entity_id=None, merged_into_id=None)
        )
        await s.flush()
        entity_ids = (
            (
                await s.execute(
                    select(NamedEntityDB.id).where(
                        NamedEntityDB.canonical_name_normalized.like(f"{PREFIX}%")
                    )
                )
            )
            .scalars()
            .all()
        )
        for eid in entity_ids:
            await s.execute(delete(EntityAliasDB).where(EntityAliasDB.entity_id == eid))
        await s.execute(
            delete(NamedEntityDB).where(
                NamedEntityDB.canonical_name_normalized.like(f"{PREFIX}%")
            )
        )
        await s.execute(delete(VideoTagDB).where(VideoTagDB.tag.like(f"{PREFIX}%")))
        await s.execute(
            delete(TagAliasDB).where(TagAliasDB.normalized_form.like(f"{PREFIX}%"))
        )
        await s.execute(
            delete(CanonicalTagDB).where(
                CanonicalTagDB.normalized_form.like(f"{PREFIX}%")
            )
        )
        await s.commit()


async def _make_tag(
    factory: async_sessionmaker[AsyncSession],
    normalized_form: str,
    *,
    raw_forms: list[str],
    video_ids: list[str],
) -> uuid.UUID:
    """Create an active canonical tag with raw forms and real video links."""
    tag_id = uuid.UUID(bytes=uuid7().bytes)
    async with factory() as s:
        s.add(
            CanonicalTagDB(
                id=tag_id,
                canonical_form=normalized_form,
                normalized_form=normalized_form,
                alias_count=len(raw_forms),
                video_count=len(video_ids),
                status="active",
            )
        )
        await s.commit()
        for raw in raw_forms:
            s.add(
                TagAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    raw_form=raw,
                    normalized_form=normalized_form,
                    canonical_tag_id=tag_id,
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
        for order, vid in enumerate(video_ids):
            s.add(VideoTagDB(video_id=vid, tag=raw_forms[0], tag_order=order))
        await s.commit()
    return tag_id


@pytest.fixture
async def real_video_ids(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    """Seed four videos so counts move for real.

    The integration database holds no videos of its own, so a fixture that
    borrowed existing rows would silently produce zero counts everywhere and
    every count assertion would pass vacuously.
    """
    from datetime import UTC, datetime

    from chronovista.db.models import Channel as ChannelDB
    from chronovista.db.models import Video as VideoDB

    channel_id = f"UC{PREFIX}TagTestChannel00"[:24]
    ids = [f"{PREFIX}vid{i}"[:20] for i in range(4)]
    async with integration_session_factory() as s:
        if await s.get(ChannelDB, channel_id) is None:
            s.add(ChannelDB(channel_id=channel_id, title="Ect064 Test Channel"))
            await s.commit()
        for vid in ids:
            if await s.get(VideoDB, vid) is None:
                s.add(
                    VideoDB(
                        video_id=vid,
                        channel_id=channel_id,
                        title=f"Ect064 Test Video {vid}",
                        upload_date=datetime(2026, 1, 1, tzinfo=UTC),
                        duration=60,
                        availability_status="available",
                    )
                )
        await s.commit()
    return ids


@pytest.fixture
async def entity_with_tag(
    integration_session_factory: async_sessionmaker[AsyncSession],
    real_video_ids: list[str],
) -> AsyncGenerator[dict[str, Any], None]:
    """An entity whose linked tag is TAG_MAIN, plus two unlinked tags.

    TAG_MAIN deliberately holds **fewer** videos than TAG_OTHER so FR-003 (the
    entity's tag always wins, irrespective of size) is exercised by default
    rather than only in the test that names it.
    """
    await _purge(integration_session_factory)
    entity_id = uuid.UUID(bytes=uuid7().bytes)
    main_id = await _make_tag(
        integration_session_factory,
        TAG_MAIN,
        raw_forms=[f"{PREFIX} Harbour Board"],
        video_ids=real_video_ids[:1],
    )
    other_id = await _make_tag(
        integration_session_factory,
        TAG_OTHER,
        raw_forms=[f"{PREFIX} Harbour Brd", f"{PREFIX} harbour brd"],
        video_ids=real_video_ids[1:4],
    )
    third_id = await _make_tag(
        integration_session_factory,
        TAG_THIRD,
        raw_forms=[f"{PREFIX} The Harbour Board"],
        video_ids=[],
    )
    async with integration_session_factory() as s:
        s.add(
            NamedEntityDB(
                id=entity_id,
                canonical_name=ENTITY_NAME,
                canonical_name_normalized=ENTITY_NORM,
                entity_type="organization",
                status="active",
            )
        )
        await s.commit()
        tag = await s.get(CanonicalTagDB, main_id)
        assert tag is not None
        tag.entity_id = entity_id
        tag.entity_type = "organization"
        s.add(tag)
        await s.commit()

    yield {
        "entity_id": entity_id,
        "main_id": main_id,
        "other_id": other_id,
        "third_id": third_id,
    }
    await _purge(integration_session_factory)


@pytest.fixture
async def entity_without_tag(
    integration_session_factory: async_sessionmaker[AsyncSession],
    real_video_ids: list[str],
) -> AsyncGenerator[dict[str, Any], None]:
    """An entity with no tag at all — the state that opened #183."""
    await _purge(integration_session_factory)
    entity_id = uuid.UUID(bytes=uuid7().bytes)
    other_id = await _make_tag(
        integration_session_factory,
        TAG_OTHER,
        raw_forms=[f"{PREFIX} Harbour Brd"],
        video_ids=real_video_ids[:3],
    )
    async with integration_session_factory() as s:
        s.add(
            NamedEntityDB(
                id=entity_id,
                canonical_name=ENTITY_NAME,
                canonical_name_normalized=ENTITY_NORM,
                entity_type="organization",
                status="active",
            )
        )
        await s.commit()
    yield {"entity_id": entity_id, "other_id": other_id}
    await _purge(integration_session_factory)


async def _counts(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> dict[str, int]:
    """Alias and mention counts for an entity, for before/after comparison."""
    async with factory() as s:
        aliases = (
            await s.execute(
                select(func.count())
                .select_from(EntityAliasDB)
                .where(EntityAliasDB.entity_id == entity_id)
            )
        ).scalar_one()
        entity = await s.get(NamedEntityDB, entity_id)
        return {
            "aliases": aliases,
            "mentions": entity.mention_count if entity else -1,
            "name": entity.canonical_name if entity else "",
            "etype": entity.entity_type if entity else "",
        }


# ---------------------------------------------------------------------------
# US1 — merge into the entity's existing tag
# ---------------------------------------------------------------------------


class TestAddTagMerges:
    async def test_merges_into_the_entitys_tag(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """US1 scenarios 1-2: source becomes merged, raw forms transfer."""
        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 201, r.text
        body = r.json()["data"]
        assert body["operation"] == "merge"
        assert body["target_normalized_form"] == TAG_MAIN

        async with integration_session_factory() as s:
            source = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert source is not None
            assert source.status == "merged"
            assert source.merged_into_id == entity_with_tag["main_id"]
            assert (
                await s.execute(
                    select(func.count())
                    .select_from(TagAliasDB)
                    .where(TagAliasDB.canonical_tag_id == source.id)
                )
            ).scalar_one() == 0, "raw forms did not transfer"

            moved = (
                await s.execute(
                    select(func.count())
                    .select_from(TagAliasDB)
                    .where(TagAliasDB.canonical_tag_id == entity_with_tag["main_id"])
                )
            ).scalar_one()
            assert moved == 3, "target should hold its own form plus both moved"

    async def test_the_entitys_tag_wins_even_when_smaller(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-003 / US1 scenario 3. The fixture makes the target the smaller tag."""
        async with integration_session_factory() as s:
            main = await s.get(CanonicalTagDB, entity_with_tag["main_id"])
            other = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert main is not None and other is not None
            assert main.video_count < other.video_count, "precondition"

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["target_normalized_form"] == TAG_MAIN

    async def test_leaves_exactly_one_active_linked_tag(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """SC-002 / invariant I1 — the defect this feature exists to correct.

        Queried without a status filter, per FR-028: the invariant must hold on
        the column itself, not only for callers who remember to filter.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        async with integration_session_factory() as s:
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(CanonicalTagDB)
                    .where(CanonicalTagDB.entity_id == entity_with_tag["entity_id"])
                )
            ).scalar_one()
            assert n == 1, (
                "the entity carries more than one linked tag; this is the "
                "parallel-link defect returning (SC-002)"
            )

    async def test_no_merged_tag_keeps_a_link_or_a_raw_form(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """SC-008 — invariants I2 and I3."""
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        async with integration_session_factory() as s:
            bad_link = (
                await s.execute(
                    select(func.count())
                    .select_from(CanonicalTagDB)
                    .where(
                        CanonicalTagDB.status == "merged",
                        CanonicalTagDB.entity_id.is_not(None),
                    )
                )
            ).scalar_one()
            assert bad_link == 0
            stranded = (
                await s.execute(
                    select(func.count())
                    .select_from(TagAliasDB)
                    .join(
                        CanonicalTagDB,
                        CanonicalTagDB.id == TagAliasDB.canonical_tag_id,
                    )
                    .where(CanonicalTagDB.status == "merged")
                )
            ).scalar_one()
            assert stranded == 0

    async def test_touches_neither_aliases_nor_mentions_nor_the_entity(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """SC-003, SC-007, FR-005 — measured across the operation."""
        before = await _counts(
            integration_session_factory, entity_with_tag["entity_id"]
        )
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        after = await _counts(integration_session_factory, entity_with_tag["entity_id"])
        assert after["aliases"] == before["aliases"], "a tag operation wrote an alias"
        assert after["mentions"] == before["mentions"]
        assert after["name"] == before["name"]
        assert after["etype"] == before["etype"]

    async def test_a_source_that_absorbed_others_carries_everything_across(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """US1 scenario 4 — transitive structure."""
        # Fold THIRD into OTHER first, so OTHER owns an inherited form.
        async with integration_session_factory() as s:
            third = await s.get(CanonicalTagDB, entity_with_tag["third_id"])
            assert third is not None
            await s.execute(
                TagAliasDB.__table__.update()
                .where(TagAliasDB.canonical_tag_id == third.id)
                .values(
                    canonical_tag_id=entity_with_tag["other_id"],
                    normalized_form=TAG_OTHER,
                )
            )
            third.status = "merged"
            third.merged_into_id = entity_with_tag["other_id"]
            s.add(third)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 201, r.text

        async with integration_session_factory() as s:
            forms = (
                (
                    await s.execute(
                        select(TagAliasDB.raw_form).where(
                            TagAliasDB.canonical_tag_id == entity_with_tag["main_id"]
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert (
                f"{PREFIX} The Harbour Board" in forms
            ), "a form inherited by the source did not follow it to the target"

    async def test_the_added_tag_leaves_the_search_results(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-009, SC-004, US1 scenario 2 — asserted over the search endpoint.

        Database state alone cannot catch this. The reappearing tag is the most
        visible symptom of the superseded behaviour.
        """
        before = await async_client.get(
            f"/api/v1/canonical-tags?q={PREFIX}&match_mode=contains&exclude_linked=true"
        )
        assert TAG_OTHER in [t["normalized_form"] for t in before.json()["data"]]

        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )

        after = await async_client.get(
            f"/api/v1/canonical-tags?q={PREFIX}&match_mode=contains&exclude_linked=true"
        )
        forms = [t["normalized_form"] for t in after.json()["data"]]
        assert TAG_OTHER not in forms, "a merged tag came back in search"
        assert TAG_MAIN not in forms, "the entity's own tag is offered to itself"


# ---------------------------------------------------------------------------
# US2 — link the first tag
# ---------------------------------------------------------------------------


class TestAddTagLinks:
    async def test_links_when_the_entity_has_no_tag(
        self,
        async_client: AsyncClient,
        entity_without_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-001 — and SC-001: the entity's video count must reflect it."""
        before = await _counts(
            integration_session_factory, entity_without_tag["entity_id"]
        )

        r = await async_client.post(
            f"/api/v1/entities/{entity_without_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 201, r.text
        body = r.json()["data"]
        assert body["operation"] == "link"
        assert body["entity_video_count"] == 3, "the linked tag's videos now count"

        async with integration_session_factory() as s:
            tag = await s.get(CanonicalTagDB, entity_without_tag["other_id"])
            assert tag is not None
            assert tag.status == "active", "linking must not deprecate the tag"
            assert tag.entity_id == entity_without_tag["entity_id"]

        after = await _counts(
            integration_session_factory, entity_without_tag["entity_id"]
        )
        assert (
            after["aliases"] == before["aliases"]
        ), "linking created an entity alias — the regression that started this"

    async def test_a_second_tag_then_merges_rather_than_linking_again(
        self,
        async_client: AsyncClient,
        entity_without_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """US2 scenario 2 — the boundary between US2 and US1."""
        await async_client.post(
            f"/api/v1/entities/{entity_without_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        await _make_tag(
            integration_session_factory,
            TAG_MAIN,
            raw_forms=[f"{PREFIX} Harbour Board"],
            video_ids=[],
        )
        r = await async_client.post(
            f"/api/v1/entities/{entity_without_tag['entity_id']}/tags",
            json={"normalized_form": TAG_MAIN},
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["operation"] == "merge"
        assert r.json()["data"]["target_normalized_form"] == TAG_OTHER


# ---------------------------------------------------------------------------
# Errors (T014a)
# ---------------------------------------------------------------------------


class TestAddTagErrors:
    async def test_missing_entity_names_the_entity(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """The service reports both misses identically; only the router can tell."""
        r = await async_client.post(
            f"/api/v1/entities/{uuid.UUID(bytes=uuid7().bytes)}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 404, r.text
        detail = r.json()["detail"].replace(" ", "")
        assert "NamedEntity" in detail
        assert "CanonicalTag" not in detail

    async def test_missing_tag_names_the_tag(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": f"{PREFIX} does not exist"},
        )
        assert r.status_code == 404, r.text
        detail = r.json()["detail"].replace(" ", "")
        assert "CanonicalTag" in detail
        assert "NamedEntity" not in detail

    async def test_a_tag_already_owned_by_another_entity_is_refused(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Acting on it would steal it (FR-007's write-side counterpart)."""
        other_entity = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as s:
            s.add(
                NamedEntityDB(
                    id=other_entity,
                    canonical_name=f"{ENTITY_NAME} Two",
                    canonical_name_normalized=f"{ENTITY_NORM} two",
                    entity_type="organization",
                    status="active",
                )
            )
            await s.commit()
            tag = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert tag is not None
            tag.entity_id = other_entity
            s.add(tag)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 409, r.text
        assert "Two" in r.json()["detail"], "the error must name who holds it"

    async def test_the_entitys_own_tag_cannot_be_added_to_itself(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_MAIN},
        )
        assert r.status_code == 422, r.text

    async def test_several_linked_tags_leaves_no_defined_target(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-002a — refuse rather than guess which tag represents the entity."""
        async with integration_session_factory() as s:
            third = await s.get(CanonicalTagDB, entity_with_tag["third_id"])
            assert third is not None
            third.entity_id = entity_with_tag["entity_id"]
            s.add(third)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 409, r.text
        assert "2 linked tags" in r.json()["detail"]

    async def test_a_merged_tag_cannot_be_attached(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with integration_session_factory() as s:
            tag = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert tag is not None
            tag.status = "merged"
            tag.merged_into_id = entity_with_tag["main_id"]
            s.add(tag)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 409, r.text
        assert "merged" in r.json()["detail"]

    async def test_fields_this_endpoint_does_not_accept_are_refused(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """Unknown fields are rejected, not silently dropped (FR-004).

        ``display_name`` and ``entity_type`` are exactly the fields a caller
        would reach for from the older classify endpoint, and dropping them
        quietly would leave that caller believing they took effect. On classify
        one of them was not inert — it wrote an alias onto the target entity —
        which is the defect this whole feature corrects.
        """
        for extra in ({"display_name": "Something Else"}, {"entity_type": "person"}):
            r = await async_client.post(
                f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
                json={"normalized_form": TAG_OTHER, **extra},
            )
            assert r.status_code == 422, f"{extra} was accepted: {r.text}"

    async def test_no_error_detail_contains_cli_vocabulary(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-020 — clients render detail verbatim, so its wording is API."""
        responses = [
            await async_client.post(
                f"/api/v1/entities/{uuid.UUID(bytes=uuid7().bytes)}/tags",
                json={"normalized_form": TAG_OTHER},
            ),
            await async_client.post(
                f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
                json={"normalized_form": TAG_MAIN},
            ),
        ]
        for r in responses:
            detail = r.json().get("detail", "")
            assert "--force" not in detail
            assert "--link-entity" not in detail


# ---------------------------------------------------------------------------
# Cross-feature contracts (T020) — constitution NON-NEGOTIABLE
# ---------------------------------------------------------------------------


class TestCrossFeatureContracts:
    async def test_every_consumer_path_still_returns_correctly_after_a_merge(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Queries through each consumer named in spec §Cross-Feature Contracts.

        Asserting the mutation happened is not enough: every defect that has
        shipped here lived in a seam, where the mutation was correct and a
        reader's assumption about it was not.
        """
        entity_id = entity_with_tag["entity_id"]

        r = await async_client.post(
            f"/api/v1/entities/{entity_id}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        assert r.status_code == 201, r.text

        # Consumer 1 — entity counting (#169) reads canonical_tags.entity_id.
        async with integration_session_factory() as s:
            linked = (
                (
                    await s.execute(
                        select(CanonicalTagDB).where(
                            CanonicalTagDB.entity_id == entity_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(linked) == 1
            assert linked[0].video_count == 4, "counts not recomputed (FR-029)"

        # Consumer 2 — canonical-tag search excludes merged tags.
        search = await async_client.get(
            f"/api/v1/canonical-tags?q={PREFIX}&match_mode=contains"
        )
        assert TAG_OTHER not in [t["normalized_form"] for t in search.json()["data"]]

        # Consumer 3 — the videos-by-tag path resolves raw forms to the target.
        vids = await async_client.get(f"/api/v1/canonical-tags/{TAG_MAIN}/videos")
        assert vids.status_code == 200, vids.text
        assert vids.json()["pagination"]["total"] == 4, (
            "videos that reached the entity through the source's raw forms "
            "are no longer reachable through the target"
        )

        # Consumer 4 — the entity detail endpoint.
        detail = await async_client.get(f"/api/v1/entities/{entity_id}")
        assert detail.status_code == 200, detail.text

        # Consumer 5 — mention detection reads entity_aliases, untouched.
        counts = await _counts(integration_session_factory, entity_id)
        assert counts["aliases"] == 0


# ---------------------------------------------------------------------------
# US3 — see which tag represents the entity (T037)
# ---------------------------------------------------------------------------


class TestGetEntityTags:
    async def test_reports_the_linked_tag(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-010 — the question that precedes every other action here."""
        r = await async_client.get(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags"
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["needs_attention"] is False
        assert len(data["linked_tags"]) == 1
        assert data["linked_tags"][0]["normalized_form"] == TAG_MAIN
        assert data["linked_tags"][0]["merged_tags"] == []

    async def test_an_entity_with_no_tag_returns_an_empty_list(
        self,
        async_client: AsyncClient,
        entity_without_tag: dict[str, Any],
    ) -> None:
        """FR-011 — empty is a meaningful answer, not an error.

        It is the signal that the entity's video count omits every
        tag-associated video, which is the state that opened #183.
        """
        r = await async_client.get(
            f"/api/v1/entities/{entity_without_tag['entity_id']}/tags"
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["linked_tags"] == []
        assert r.json()["data"]["needs_attention"] is False

    async def test_lists_what_the_tag_has_absorbed(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-012/FR-013 — and the operation needed to reverse each."""
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        r = await async_client.get(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags"
        )
        assert r.status_code == 200, r.text
        linked = r.json()["data"]["linked_tags"]
        assert len(linked) == 1
        merged = linked[0]["merged_tags"]
        assert len(merged) == 1
        assert merged[0]["normalized_form"] == TAG_OTHER
        assert (
            merged[0]["operation_id"] is not None
        ), "without the operation the tag cannot be un-merged from the browser"
        assert (
            merged[0]["operation_source_count"] == 1
        ), "a single-source merge needs no confirmation to reverse (FR-016)"

    async def test_the_absorbed_count_is_frozen_not_live(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-014 — a merged tag owns no videos, so a live count would be 0.

        Reporting 0 would tell the curator the tag brought nothing, when it
        brought three. The figure is its pre-merge contribution.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        r = await async_client.get(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags"
        )
        merged = r.json()["data"]["linked_tags"][0]["merged_tags"][0]
        assert merged["contributed_video_count"] == 3

    async def test_several_linked_tags_are_all_listed_and_flagged(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-011a — render the legacy state rather than raise on it."""
        async with integration_session_factory() as s:
            third = await s.get(CanonicalTagDB, entity_with_tag["third_id"])
            assert third is not None
            third.entity_id = entity_with_tag["entity_id"]
            s.add(third)
            await s.commit()

        r = await async_client.get(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags"
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["needs_attention"] is True
        forms = {t["normalized_form"] for t in data["linked_tags"]}
        assert forms == {TAG_MAIN, TAG_THIRD}

    async def test_a_missing_entity_is_a_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        r = await async_client.get(
            f"/api/v1/entities/{uuid.UUID(bytes=uuid7().bytes)}/tags"
        )
        assert r.status_code == 404, r.text

    async def test_an_un_merged_tag_stops_being_listed(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A reversed merge must not leave the tag showing as absorbed.

        The operation lookup skips reversed operations; this checks the listing
        follows the tag's own state rather than the stale operation log.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        async with integration_session_factory() as s:
            source = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert source is not None
            source.status = "active"
            source.merged_into_id = None
            s.add(source)
            await s.commit()

        r = await async_client.get(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags"
        )
        assert r.json()["data"]["linked_tags"][0]["merged_tags"] == []


# ---------------------------------------------------------------------------
# US4 — un-merge and unlink (T043-T046, T049)
# ---------------------------------------------------------------------------


class TestUnMerge:
    async def test_restores_the_tag_and_its_link(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-015 and FR-027 — status, merged_into_id, raw forms, entity link."""
        # Give the source an entity link before merging, so FR-027's restore is
        # exercised rather than trivially satisfied by it being null.
        async with integration_session_factory() as s:
            other = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert other is not None
            other.entity_id = None
            s.add(other)
            await s.commit()

        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["restored"] == [TAG_OTHER]

        async with integration_session_factory() as s:
            tag = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert tag is not None
            assert tag.status == "active"
            assert tag.merged_into_id is None
            forms = (
                (
                    await s.execute(
                        select(TagAliasDB.raw_form).where(
                            TagAliasDB.canonical_tag_id == tag.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(forms) == 2, "its own raw forms did not come back"

    async def test_forms_that_arrived_later_stay_on_the_target(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Only the forms recorded at merge time return (data-model §Un-merge).

        A form that landed on the target afterwards was never the source's, and
        handing it over would be inventing history.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        async with integration_session_factory() as s:
            s.add(
                TagAliasDB(
                    id=uuid.UUID(bytes=uuid7().bytes),
                    raw_form=f"{PREFIX} Arrived Later",
                    normalized_form=TAG_MAIN,
                    canonical_tag_id=entity_with_tag["main_id"],
                    creation_method="auto_normalize",
                    occurrence_count=1,
                )
            )
            await s.commit()

        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )

        async with integration_session_factory() as s:
            target_forms = (
                (
                    await s.execute(
                        select(TagAliasDB.raw_form).where(
                            TagAliasDB.canonical_tag_id == entity_with_tag["main_id"]
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert f"{PREFIX} Arrived Later" in target_forms

    async def test_the_restored_tag_is_searchable_again(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-019, SC-006 — the loop closes without the CLI."""
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        gone = await async_client.get(
            f"/api/v1/canonical-tags?q={PREFIX}&match_mode=contains&exclude_linked=true"
        )
        assert TAG_OTHER not in [t["normalized_form"] for t in gone.json()["data"]]

        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        back = await async_client.get(
            f"/api/v1/canonical-tags?q={PREFIX}&match_mode=contains&exclude_linked=true"
        )
        assert TAG_OTHER in [t["normalized_form"] for t in back.json()["data"]]

    async def test_a_multi_source_merge_names_every_tag_it_would_restore(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-016 — a count alone cannot be judged, so the names are required."""
        from chronovista.repositories.canonical_tag_repository import (
            CanonicalTagRepository,
        )
        from chronovista.repositories.entity_alias_repository import (
            EntityAliasRepository,
        )
        from chronovista.repositories.named_entity_repository import (
            NamedEntityRepository,
        )
        from chronovista.repositories.tag_alias_repository import TagAliasRepository
        from chronovista.repositories.tag_operation_log_repository import (
            TagOperationLogRepository,
        )
        from chronovista.services.tag_management import TagManagementService

        service = TagManagementService(
            canonical_tag_repo=CanonicalTagRepository(),
            tag_alias_repo=TagAliasRepository(),
            named_entity_repo=NamedEntityRepository(),
            entity_alias_repo=EntityAliasRepository(),
            operation_log_repo=TagOperationLogRepository(),
        )
        async with integration_session_factory() as s:
            await service.merge(s, [TAG_OTHER, TAG_THIRD], TAG_MAIN)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "1 other tag" in detail
        # The name, not just the number — whether this is acceptable depends on
        # which tag comes back.
        assert TAG_THIRD.title() in detail or TAG_THIRD in detail

        confirmed = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={"confirm_multi_source": True},
        )
        assert confirmed.status_code == 200, confirmed.text

    async def test_a_second_reversal_is_refused(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-031 — preconditions are re-checked against current state."""
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        first = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        assert first.status_code == 200, first.text
        second = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        assert second.status_code == 404, second.text

    async def test_a_tag_merged_elsewhere_cannot_be_reversed_from_here(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """One entity's page must not mutate another entity's tag group."""
        async with integration_session_factory() as s:
            third = await s.get(CanonicalTagDB, entity_with_tag["third_id"])
            other = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert third is not None and other is not None
            third.status = "merged"
            third.merged_into_id = other.id  # merged into an *unlinked* tag
            s.add(third)
            await s.commit()

        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_THIRD}/un-merge",
            json={},
        )
        assert r.status_code == 404, r.text


class TestUnlink:
    async def test_clears_the_link_without_deleting_the_tag(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-018 — the tag returns to the pool rather than being deprecated."""
        r = await async_client.delete(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_MAIN}"
        )
        assert r.status_code == 200, r.text

        async with integration_session_factory() as s:
            tag = await s.get(CanonicalTagDB, entity_with_tag["main_id"])
            assert tag is not None
            assert tag.entity_id is None
            assert tag.status == "active", "unlink must not deprecate the tag"

    async def test_is_refused_while_tags_are_merged_into_it(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        """FR-017 — unlinking would strand the whole group's raw forms.

        Those forms live on this tag now, so a single click naming one tag
        would take every merged tag's videos away from the entity too.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        r = await async_client.delete(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_MAIN}"
        )
        assert r.status_code == 409, r.text
        assert "Un-merge" in r.json()["detail"]

    async def test_permitted_once_the_group_is_empty(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}/un-merge",
            json={},
        )
        r = await async_client.delete(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_MAIN}"
        )
        assert r.status_code == 200, r.text

    async def test_a_tag_not_representing_this_entity_is_a_404(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
    ) -> None:
        r = await async_client.delete(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags/{TAG_OTHER}"
        )
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Phase 7 — cross-cutting invariants (T055-T058)
# ---------------------------------------------------------------------------


class TestInvariants:
    async def test_a_failed_attach_moves_no_raw_forms(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-030 — atomicity, checked at the state it would corrupt.

        The partial state that matters is raw forms moved to the target without
        the source being marked merged: the source would then own nothing while
        still appearing active and searchable, and its videos would reach the
        entity through a tag nobody links to it.
        """
        async with integration_session_factory() as s:
            before = (
                (
                    await s.execute(
                        select(TagAliasDB.canonical_tag_id).where(
                            TagAliasDB.normalized_form.like(f"{PREFIX}%")
                        )
                    )
                )
                .scalars()
                .all()
            )

        # Refused for a reason the router raises before touching the service.
        r = await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_MAIN},
        )
        assert r.status_code == 422, r.text

        async with integration_session_factory() as s:
            after = (
                (
                    await s.execute(
                        select(TagAliasDB.canonical_tag_id).where(
                            TagAliasDB.normalized_form.like(f"{PREFIX}%")
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert sorted(map(str, before)) == sorted(map(str, after))

    async def test_counts_match_the_rows_they_summarize(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-029 / invariant I6 — on the **active** tag after a merge.

        FR-010 shows the linked tag's video count, which is only meaningful if
        the denormalized value agrees with the rows underneath it.

        The merged source is deliberately excluded: it owns no rows, so a
        recomputed count would be zero, and that stored value is exactly what
        FR-014 reports as what the tag contributed. Zeroing it would tell a
        curator the tag brought nothing when it brought three videos. Both
        halves are asserted here, because the pair is easy to "fix" in the
        wrong direction.
        """
        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        async with integration_session_factory() as s:
            target = await s.get(CanonicalTagDB, entity_with_tag["main_id"])
            assert target is not None
            real_aliases = (
                await s.execute(
                    select(func.count())
                    .select_from(TagAliasDB)
                    .where(TagAliasDB.canonical_tag_id == target.id)
                )
            ).scalar_one()
            real_videos = (
                await s.execute(
                    select(func.count(func.distinct(VideoTagDB.video_id)))
                    .select_from(VideoTagDB)
                    .join(TagAliasDB, VideoTagDB.tag == TagAliasDB.raw_form)
                    .where(TagAliasDB.canonical_tag_id == target.id)
                )
            ).scalar_one()
            assert target.alias_count == real_aliases
            assert target.video_count == real_videos

            source = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert source is not None
            assert source.video_count == 3, (
                "the merged tag's snapshot was recomputed away; FR-014 would "
                "then report that it contributed nothing"
            )

    async def test_a_merge_leaves_the_sources_entity_type_alone(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-026a — unlike the link, a type is meaningful without an entity.

        Tag-only classifications (topic, descriptor) carry one with no link at
        all, so clearing it would revoke a classification the merge was not
        asked to touch.
        """
        async with integration_session_factory() as s:
            other = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert other is not None
            other.entity_type = "organization"
            s.add(other)
            await s.commit()

        await async_client.post(
            f"/api/v1/entities/{entity_with_tag['entity_id']}/tags",
            json={"normalized_form": TAG_OTHER},
        )

        async with integration_session_factory() as s:
            merged = await s.get(CanonicalTagDB, entity_with_tag["other_id"])
            assert merged is not None
            assert merged.status == "merged"
            assert merged.entity_id is None, "the link must be cleared (FR-026)"
            assert (
                merged.entity_type == "organization"
            ), "the type must survive (FR-026a)"

    async def test_aliases_predating_this_feature_survive_every_operation(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-004a — a negative requirement needs a guard more than a positive.

        Nothing would fail today if a future change added "cleanup" that
        deleted aliases it did not create, and an operation removing aliases it
        never made is indistinguishable from the defect this feature corrects.
        """
        entity_id = entity_with_tag["entity_id"]
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        async with integration_session_factory() as s:
            s.add(
                EntityAliasDB(
                    id=alias_id,
                    entity_id=entity_id,
                    alias_name="Ect064 Pre-Existing Alias",
                    alias_name_normalized="ect064 pre-existing alias",
                    alias_type="name_variant",
                    occurrence_count=0,
                )
            )
            await s.commit()

        await async_client.post(
            f"/api/v1/entities/{entity_id}/tags",
            json={"normalized_form": TAG_OTHER},
        )
        await async_client.post(
            f"/api/v1/entities/{entity_id}/tags/{TAG_OTHER}/un-merge", json={}
        )
        await async_client.delete(f"/api/v1/entities/{entity_id}/tags/{TAG_MAIN}")

        async with integration_session_factory() as s:
            survivor = await s.get(EntityAliasDB, alias_id)
            assert (
                survivor is not None
            ), "an operation deleted an alias it did not create"
            assert survivor.alias_name == "Ect064 Pre-Existing Alias"

    async def test_no_error_from_any_endpoint_speaks_cli(
        self,
        async_client: AsyncClient,
        entity_with_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """FR-020 across all four endpoints — clients render detail verbatim."""
        entity_id = entity_with_tag["entity_id"]
        missing = str(uuid.UUID(bytes=uuid7().bytes))

        await async_client.post(
            f"/api/v1/entities/{entity_id}/tags",
            json={"normalized_form": TAG_OTHER},
        )

        responses = [
            await async_client.post(
                f"/api/v1/entities/{missing}/tags",
                json={"normalized_form": TAG_OTHER},
            ),
            await async_client.post(
                f"/api/v1/entities/{entity_id}/tags",
                json={"normalized_form": TAG_MAIN},
            ),
            await async_client.get(f"/api/v1/entities/{missing}/tags"),
            await async_client.post(
                f"/api/v1/entities/{entity_id}/tags/{TAG_THIRD}/un-merge", json={}
            ),
            await async_client.delete(f"/api/v1/entities/{entity_id}/tags/{TAG_MAIN}"),
        ]
        for r in responses:
            detail = str(r.json().get("detail", ""))
            for flag in ("--force", "--link-entity", "--type", "chronovista tags"):
                assert (
                    flag not in detail
                ), f"{flag} leaked into {r.status_code}: {detail}"
