"""Integration tests for the on-grounding Wikipedia image fallback (Feature 094).

Crosses the REAL `enrich_on_approval` path against a real database: the step is actually reached
after the Wikidata property write, the write lands via `replace_properties`, and the real
`merge_wikidata_blocks` governs precedence. Only the external boundaries are mocked — the Wikidata
client (`client_factory`), the DBpedia resolver (`dbpedia_factory`, returns nothing so
`_store_categories` is an offline no-op), and the image gate (`image_fallback_factory` → a real
`WikipediaImageFallback` driven by an `httpx.MockTransport`). Neutral placeholders / synthetic
filenames only (Constitution VI).
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.services import wikidata_properties as wp
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from chronovista.services.wikipedia_image_fallback import WikipediaImageFallback

pytestmark = pytest.mark.asyncio

_SET_AT = "2026-10-25T00:00:00+00:00"


class _Client:
    """A fake Wikidata client whose `fetch_properties` returns a configured bag."""

    def __init__(self, bag: dict[str, Any]) -> None:
        self._bag = bag

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return self._bag


class _NoDbpedia:
    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


def _free_commons_transport() -> httpx.MockTransport:
    """A Wikimedia transport that yields a free Commons lead image for any QID."""

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        params = request.url.params
        if "wikidata.org/w/api.php" in url:
            qid = params.get("ids")
            return httpx.Response(
                200,
                json={
                    "entities": {
                        qid: {"sitelinks": {"enwiki": {"title": "Placeholder Subject"}}}
                    }
                },
            )
        if "en.wikipedia.org/w/api.php" in url:
            if params.get("prop") == "pageprops":
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": {
                                "1": {
                                    "pageid": 1,
                                    "pageprops": {
                                        "page_image_free": "Free_Commons_Portrait.jpg"
                                    },
                                }
                            }
                        }
                    },
                )
            if params.get("prop") == "imageinfo":
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": {
                                "1": {
                                    "imagerepository": "shared",
                                    "imageinfo": [{"extmetadata": {}}],
                                }
                            }
                        }
                    },
                )
        return httpx.Response(200, json={})

    return httpx.MockTransport(respond)


def _service(
    db_session: AsyncSession, *, bag: dict[str, Any]
) -> tuple[EntityEnrichmentService, async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    service = EntityEnrichmentService(
        factory,
        client_factory=lambda: _Client(bag),
        dbpedia_factory=lambda: _NoDbpedia(),
        image_fallback_factory=lambda: WikipediaImageFallback(
            http=httpx.AsyncClient(transport=_free_commons_transport())
        ),
    )
    return service, factory


async def _seed(db_session: AsyncSession, properties: dict[str, Any]) -> uuid.UUID:
    entity = NamedEntityDB(
        canonical_name=f"Placeholder {uuid.uuid4().hex[:8]}",
        canonical_name_normalized=f"placeholder {uuid.uuid4().hex[:8]}",
        entity_type="person",
        status="active",
        external_ids={
            "wikidata": {"id": "Q000001", "verified": True, "status": "verified"}
        },
        properties=properties,
    )
    db_session.add(entity)
    await db_session.commit()
    return uuid.UUID(str(entity.id))


async def _read_properties(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> dict[str, Any]:
    async with factory() as s:
        row = (
            await s.execute(select(NamedEntityDB).where(NamedEntityDB.id == entity_id))
        ).scalar_one()
        return dict(row.properties or {})


# A no-image Wikidata bag (no P18) and a P18-bearing one.
_NO_P18: dict[str, Any] = {
    "occupation": wp.assemble_block([], ["analyst"], {}, _SET_AT)
}
_WITH_P18: dict[str, Any] = {
    "image": wp.assemble_block([], ["Real_P18.jpg"], {}, _SET_AT)
}


class TestAutoFillOnGrounding:
    async def test_no_p18_stores_wikipedia_image(
        self, db_session: AsyncSession
    ) -> None:
        """US1/FR-002: grounding with no P18 + a free-Commons page stores a source:'wikipedia' block."""
        entity_id = await _seed(db_session, {})
        service, factory = _service(db_session, bag=_NO_P18)

        await service.enrich_on_approval(entity_id, "Q000001")

        props = await _read_properties(factory, entity_id)
        assert props["image"]["source"] == "wikipedia"
        assert props["image"]["values"] == ["Free_Commons_Portrait.jpg"]
        # The Wikidata facts that landed first are preserved alongside.
        assert props["occupation"]["source"] == "wikidata"


class TestPrecedence:
    async def test_later_p18_replaces_wikipedia_image(
        self, db_session: AsyncSession
    ) -> None:
        """US2/FR-004: a refetch that yields a P18 replaces a prior source:'wikipedia' block (real merge)."""
        entity_id = await _seed(
            db_session,
            {"image": wp.wikipedia_image_block("Old_Wiki.jpg", _SET_AT)},
        )
        service, factory = _service(db_session, bag=_WITH_P18)

        await service.enrich_on_approval(entity_id, "Q000001")

        props = await _read_properties(factory, entity_id)
        assert props["image"]["source"] == "wikidata"
        assert props["image"]["values"] == ["Real_P18.jpg"]

    async def test_real_p18_write_is_not_overridden_by_the_fallback(
        self, db_session: AsyncSession
    ) -> None:
        """US2/FR-004 ordering invariant on the real path: when `_write_properties` writes a P18,
        the image step (which re-reads in its own session) must see it and SKIP — never overwrite it
        with the free-Commons image. The gate's MockTransport would store `Free_Commons_Portrait.jpg`
        if it ran, so a `wikidata`/`Real_P18.jpg` result proves the two-session read-your-write skip.
        """
        entity_id = await _seed(db_session, {})  # no prior image
        service, factory = _service(db_session, bag=_WITH_P18)

        await service.enrich_on_approval(entity_id, "Q000001")

        props = await _read_properties(factory, entity_id)
        assert props["image"]["source"] == "wikidata"
        assert props["image"]["values"] == [
            "Real_P18.jpg"
        ]  # NOT the free-Commons image


class TestRegroundReDerive:
    async def test_reground_re_derives_wikipedia_image(
        self, db_session: AsyncSession
    ) -> None:
        """US3/FR-007: after a reground clears properties, the re-enrichment re-derives the image."""
        # Start with a Wikipedia image, then simulate reground clearing the whole bag.
        entity_id = await _seed(
            db_session,
            {"image": wp.wikipedia_image_block("Old_Wiki.jpg", _SET_AT)},
        )
        async with async_sessionmaker(
            bind=db_session.bind, expire_on_commit=False
        )() as s:
            row = (
                await s.execute(
                    select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
                )
            ).scalar_one()
            row.properties = {}  # reground: replace_enrichment(properties={})
            await s.commit()

        service, factory = _service(db_session, bag=_NO_P18)
        await service.enrich_on_approval(entity_id, "Q000001")

        props = await _read_properties(factory, entity_id)
        assert props["image"]["source"] == "wikipedia"
        assert props["image"]["values"] == ["Free_Commons_Portrait.jpg"]
