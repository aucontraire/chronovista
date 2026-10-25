"""Integration tests for the Wikipedia free-Commons image backfill (Feature 093, T010/T011/T012).

Crosses the REAL seams the backfill depends on: the candidate query, the ``source:"wikipedia"``
write (``wikipedia_image_block`` -> ``replace_properties`` -> commit — the command's exact inner
expression), the property-refetch merge (``merge_wikidata_blocks``), and the read-back through the
entity detail + image-serving endpoints. The Wikimedia gate is exercised for real via an injected
``httpx.MockTransport`` (no network); the gate's own accept/decline logic is unit-tested separately.

Like ``test_entity_wikidata_backfill_capture.py``, this does NOT drive the whole CLI command through
CliRunner: ``list_grounded_without_image`` sweeps the shared integration table, so a real ``--apply``
would touch other tests' rows. Each test seeds and owns its entities and applies the command's inner
write expression only to those. Neutral placeholders / synthetic filenames only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.wikipedia_image import FallbackOutcome
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services import wikidata_properties as wp
from chronovista.services.wikipedia_image_fallback import WikipediaImageFallback
from tests.factories.named_entity_orm_factory import create_named_entity_db

pytestmark = pytest.mark.asyncio

_SET_AT = "2026-10-24T00:00:00+00:00"


async def _seed_grounded_no_image(
    factory: async_sessionmaker[AsyncSession],
    *,
    qid: str,
    properties: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Seed one grounded, image-less entity and return its id."""
    suffix = uuid.uuid4().hex[:8]
    entity = create_named_entity_db(
        canonical_name=f"Placeholder Entity {suffix}",
        canonical_name_normalized=f"placeholder entity {suffix}",
        entity_type="person",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties=properties if properties is not None else {},
        manual_image_ext=None,
    )
    async with factory() as s:
        s.add(entity)
        await s.commit()
        return uuid.UUID(str(entity.id))


async def _properties_of(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> dict[str, Any]:
    async with factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        return dict(row.properties or {})


# --------------------------------------------------------------------------------------
# US1 — fill the gap: candidate selection, dry-run safety, the write, serving, idempotence
# --------------------------------------------------------------------------------------


async def test_us1_backfill_stores_and_serves_and_is_idempotent(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repo = NamedEntityRepository()
    qid = f"Q0930{uuid.uuid4().hex[:5]}"
    entity_id = await _seed_grounded_no_image(integration_session_factory, qid=qid)

    # The real candidate query finds the seeded row (membership — the shared table holds others).
    async with integration_session_factory() as s:
        selected = {e.id for e in await repo.list_grounded_without_image(s)}
    assert entity_id in selected

    # ---- Dry-run discipline: exercise the write then roll back → properties unchanged. ----
    async with integration_session_factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        merged = {
            **(row.properties or {}),
            "image": wp.wikipedia_image_block("Free_Commons_Portrait.jpg", _SET_AT),
        }
        assert merged != row.properties  # a change IS waiting (not a vacuous dry run)
        await repo.replace_properties(s, entity_id, properties=merged)
        await s.rollback()
    assert await _properties_of(integration_session_factory, entity_id) == {}

    # ---- Apply: store the source:"wikipedia" block (the command's inner expression). ----
    async with integration_session_factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        merged = {
            **(row.properties or {}),
            "image": wp.wikipedia_image_block("Free_Commons_Portrait.jpg", _SET_AT),
        }
        await repo.replace_properties(s, entity_id, properties=merged)
        await s.commit()

    stored = await _properties_of(integration_session_factory, entity_id)
    assert stored["image"]["source"] == "wikipedia"
    assert stored["image"]["values"] == ["Free_Commons_Portrait.jpg"]

    # FR-003/FR-004: the detail endpoint reads the Wikipedia block as an automated image, source-blind.
    detail = await async_client.get(f"/api/v1/entities/{entity_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["image"]["has_wikidata"] is True

    # FR-004: the existing image-serving route resolves the stored block with no resolver change.
    served = await async_client.get(f"/api/v1/images/entities/{entity_id}")
    assert served.status_code == 200

    # FR-010: now that it has an image, it is no longer a candidate (a re-run skips it).
    async with integration_session_factory() as s:
        selected_after = {e.id for e in await repo.list_grounded_without_image(s)}
    assert entity_id not in selected_after


# --------------------------------------------------------------------------------------
# US2 — never store a non-free image: a mixed run stores only the free-Commons one
# --------------------------------------------------------------------------------------


def _mixed_transport(scenarios: dict[str, dict[str, Any]]) -> httpx.MockTransport:
    """A Wikimedia transport driving the real gate: each QID maps to one accept/decline scenario."""
    by_title = {s["title"]: s for s in scenarios.values() if s.get("title")}
    by_file = {s["lead"]: s for s in scenarios.values() if s.get("lead")}

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        params = request.url.params
        if "wikidata.org/w/api.php" in url:
            qid = params.get("ids")
            sc = scenarios.get(qid or "", {})
            title = sc.get("title")
            ent = {"sitelinks": {"enwiki": {"title": title}}} if title else {}
            return httpx.Response(200, json={"entities": {qid: ent}})
        if "en.wikipedia.org/w/api.php" in url:
            prop = params.get("prop")
            if prop == "pageprops":
                sc = by_title.get(params.get("titles") or "", {})
                lead = sc.get("lead")
                pageprops = {"page_image_free": lead} if lead else {}
                return httpx.Response(
                    200,
                    json={
                        "query": {"pages": {"1": {"pageid": 1, "pageprops": pageprops}}}
                    },
                )
            if prop == "imageinfo":
                fname = (params.get("titles") or "").removeprefix("File:")
                sc = by_file.get(fname, {})
                page: dict[str, Any] = {"imagerepository": sc.get("repo")}
                extmeta = {"NonFree": {"value": "1"}} if sc.get("non_free") else {}
                page["imageinfo"] = [{"extmetadata": extmeta}]
                return httpx.Response(200, json={"query": {"pages": {"1": page}}})
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


async def test_us2_mixed_run_stores_only_free_commons(
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repo = NamedEntityRepository()
    tag = uuid.uuid4().hex[:5]
    scenarios = {
        f"Q093A{tag}": {
            "title": f"Title A {tag}",
            "lead": f"Free_A_{tag}.jpg",
            "repo": "shared",
            "non_free": False,
        },
        f"Q093B{tag}": {
            "title": f"Title B {tag}",
            "lead": f"NonFree_B_{tag}.jpg",
            "repo": "shared",
            "non_free": True,
        },
        f"Q093C{tag}": {
            "title": f"Title C {tag}",
            "lead": f"Local_C_{tag}.jpg",
            "repo": "local",
            "non_free": False,
        },
        f"Q093D{tag}": {"title": None},  # no page
        f"Q093E{tag}": {"title": f"Title E {tag}", "lead": None},  # no lead image
    }
    ids = {
        qid: await _seed_grounded_no_image(integration_session_factory, qid=qid)
        for qid in scenarios
    }

    fallback = WikipediaImageFallback(
        http=httpx.AsyncClient(transport=_mixed_transport(scenarios))
    )

    # Run the gate + the command's write expression over exactly the seeded rows.
    outcomes: dict[str, FallbackOutcome] = {}
    for qid, entity_id in ids.items():
        result = await fallback.evaluate(entity_id, qid)
        outcomes[qid] = result.outcome
        if result.outcome is FallbackOutcome.STORED and result.filename:
            async with integration_session_factory() as s:
                row = (
                    await s.execute(
                        select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                    )
                ).scalar_one()
                merged = {
                    **(row.properties or {}),
                    "image": wp.wikipedia_image_block(result.filename, _SET_AT),
                }
                await repo.replace_properties(s, entity_id, properties=merged)
                await s.commit()

    # Only the free-Commons one is STORED; the rest decline/absent — distinct outcomes (FR-007).
    assert outcomes[f"Q093A{tag}"] is FallbackOutcome.STORED
    assert outcomes[f"Q093B{tag}"] is FallbackOutcome.DECLINED_NON_FREE
    assert outcomes[f"Q093C{tag}"] is FallbackOutcome.DECLINED_NOT_COMMONS
    assert outcomes[f"Q093D{tag}"] is FallbackOutcome.NO_PAGE
    assert outcomes[f"Q093E{tag}"] is FallbackOutcome.NO_LEAD_IMAGE

    # Run-level legal invariant (SC-001): the free-Commons row got its image; EVERY other row
    # stored nothing — zero non-free / non-Commons blocks written across the whole run.
    stored_a = await _properties_of(integration_session_factory, ids[f"Q093A{tag}"])
    assert stored_a["image"]["source"] == "wikipedia"
    assert stored_a["image"]["values"] == [f"Free_A_{tag}.jpg"]
    for qid in (f"Q093B{tag}", f"Q093C{tag}", f"Q093D{tag}", f"Q093E{tag}"):
        assert await _properties_of(integration_session_factory, ids[qid]) == {}


# --------------------------------------------------------------------------------------
# US3 — behaves like the automated image: survives a refetch, overridden by a later P18
# --------------------------------------------------------------------------------------


async def test_us3_survives_refetch_and_is_overridden_by_p18(
    async_client: AsyncClient,
    integration_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repo = NamedEntityRepository()
    qid = f"Q0931{uuid.uuid4().hex[:5]}"
    entity_id = await _seed_grounded_no_image(
        integration_session_factory,
        qid=qid,
        properties={"image": wp.wikipedia_image_block("Wiki_Portrait.jpg", _SET_AT)},
    )

    # 1. A property refetch that finds NO P18 adds no "image" key → the merge preserves ours (FR-005).
    current = await _properties_of(integration_session_factory, entity_id)
    refetched_no_p18 = {
        "occupation": wp.assemble_block([], ["analyst"], {}, _SET_AT)
    }  # a fresh wikidata bag without an image
    merged = wp.merge_wikidata_blocks(current, refetched_no_p18)
    async with integration_session_factory() as s:
        await repo.replace_properties(s, entity_id, properties=merged)
        await s.commit()

    after_refetch = await _properties_of(integration_session_factory, entity_id)
    assert after_refetch["image"]["source"] == "wikipedia"
    assert after_refetch["image"]["values"] == ["Wiki_Portrait.jpg"]
    # Still served and still counted as an automated image.
    served = await async_client.get(f"/api/v1/images/entities/{entity_id}")
    assert served.status_code == 200
    detail = await async_client.get(f"/api/v1/entities/{entity_id}")
    assert detail.json()["data"]["image"]["has_wikidata"] is True

    # 2. A later refetch that DOES find P18 overlays a fresh source:"wikidata" image → Wikidata wins.
    current2 = await _properties_of(integration_session_factory, entity_id)
    refetched_p18 = {
        "image": wp.assemble_block([], ["Real_P18_Portrait.jpg"], {}, _SET_AT)
    }
    merged2 = wp.merge_wikidata_blocks(current2, refetched_p18)
    async with integration_session_factory() as s:
        await repo.replace_properties(s, entity_id, properties=merged2)
        await s.commit()

    after_p18 = await _properties_of(integration_session_factory, entity_id)
    assert after_p18["image"]["source"] == "wikidata"
    assert after_p18["image"]["values"] == ["Real_P18_Portrait.jpg"]
