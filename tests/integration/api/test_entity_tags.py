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
