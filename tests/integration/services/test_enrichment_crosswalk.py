"""Real-database seam tests for the Feature 100 foreign-only cross-walk on the enrichment seam (US1).

Drives the real ``EntityEnrichmentService.enrich_on_approval`` over the integration DB with every
external call stubbed (no live network, Constitution VI). Verifies that a grounded entity with NO
English article but a foreign one gets its cross-walked English categories automatically — on
approval and on a refresh — and that the Cross-Feature Data Contract holds (visible THROUGH the
Feature 083 shared-category bridge, not merely as rows). All titles/category names are neutral
placeholders.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityCategory, NamedEntity
from chronovista.repositories.entity_category_repository import EntityCategoryRepository
from chronovista.services.category_size import CategorySizeService
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from chronovista.services.wikidata_client import WikidataUnavailable

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

assign_repo = EntityCategoryRepository()


class _StubSizes(CategorySizeService):
    """CategorySizeService that returns no sizes (new categories keep NULL global_size)."""

    async def sizes_for(self, names: Any) -> dict[str, int]:
        return {}


class _RaisingSizes(CategorySizeService):
    """CategorySizeService whose size fetch fails — exercises the store-side best-effort branch."""

    async def sizes_for(self, names: Any) -> dict[str, int]:
        raise RuntimeError("size service down")


class _NoEnglishResolver:
    """DBpedia resolver that resolves nothing — a foreign-only entity has no English article."""

    async def resolve(self, qid: str) -> tuple[str, str] | None:
        return None


class _NoImage:
    """Image fallback stub whose outcome is never STORED (no live Wikimedia call)."""

    async def evaluate(self, entity_id: uuid.UUID, qid: str) -> Any:
        return SimpleNamespace(outcome=object(), filename=None)


class _CrosswalkWikidata:
    """Wikidata client stub: curated properties + canned sitelinks for entity and category QIDs."""

    def __init__(
        self,
        entity_sitelinks: dict[str, dict[str, str]],
        category_sitelinks: dict[str, dict[str, str]],
        *,
        fail_sitelinks: bool = False,
    ) -> None:
        self._entity = entity_sitelinks
        self._cats = category_sitelinks
        self._fail = fail_sitelinks

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        return {"occupation": {"values": ["x"], "qids": [], "source": "wikidata"}}

    async def fetch_sitelinks(self, qids: list[str]) -> dict[str, dict[str, str]]:
        if self._fail:
            raise WikidataUnavailable("knowledge base down")
        merged = {**self._entity, **self._cats}
        return {q: merged.get(q, {}) for q in qids}


class _CrosswalkFetch:
    """Per-language fetch stub: foreign article categories + their category→QID map."""

    def __init__(self, cats: dict[str, list[str]], cat_qids: dict[str, str]) -> None:
        self._cats = cats
        self._cat_qids = cat_qids

    async def categories_for_titles(self, titles: Any) -> dict[str, list[str]]:
        return {t: self._cats.get(t, []) for t in titles}

    async def wikibase_items_for_categories(self, titles: Any) -> dict[str, str]:
        return {t: self._cat_qids[t] for t in titles if t in self._cat_qids}


async def _ground_foreign_only(session: AsyncSession, qid: str) -> uuid.UUID:
    """Seed a grounded entity with a Wikidata QID, no DBpedia link, and no categories."""
    suffix = uuid.uuid4().hex[:8]
    entity = NamedEntity(
        canonical_name=f"Seam {suffix}",
        canonical_name_normalized=f"seam {suffix}",
        entity_type="person",
        status="active",
        external_ids={"wikidata": {"id": qid, "verified": True, "status": "verified"}},
        properties={},
    )
    session.add(entity)
    await session.commit()
    return uuid.UUID(str(entity.id))


def _service(
    factory: async_sessionmaker[AsyncSession],
    wikidata: _CrosswalkWikidata,
    fetch_by_lang: dict[str, _CrosswalkFetch],
    *,
    size_factory: Any = _StubSizes,
) -> EntityEnrichmentService:
    return EntityEnrichmentService(
        factory,
        client_factory=lambda: wikidata,  # type: ignore[arg-type,return-value]
        dbpedia_factory=lambda: _NoEnglishResolver(),  # type: ignore[arg-type,return-value]
        category_fetch_factory=lambda: _CrosswalkFetch({}, {}),  # type: ignore[arg-type,return-value]
        size_factory=size_factory,
        image_fallback_factory=lambda: _NoImage(),  # type: ignore[arg-type,return-value]
        crosswalk_fetch_factory=lambda lang: fetch_by_lang[lang],  # type: ignore[arg-type,return-value]
    )


async def _ground_with_dbpedia(session: AsyncSession, qid: str, iri: str) -> uuid.UUID:
    """Seed a grounded entity that carries a stored DBpedia IRI (i.e. has an English article)."""
    suffix = uuid.uuid4().hex[:8]
    entity = NamedEntity(
        canonical_name=f"Seam {suffix}",
        canonical_name_normalized=f"seam {suffix}",
        entity_type="person",
        status="active",
        external_ids={
            "wikidata": {"id": qid, "verified": True, "status": "verified"},
            "dbpedia": {"id": iri},
        },
        properties={},
    )
    session.add(entity)
    await session.commit()
    return uuid.UUID(str(entity.id))


async def _sources(
    factory: async_sessionmaker[AsyncSession], entity_id: uuid.UUID
) -> list[str]:
    async with factory() as s:
        rows = await s.execute(
            select(EntityCategory.source).where(EntityCategory.entity_id == entity_id)
        )
    return list(rows.scalars().all())


class TestForeignOnlyCrosswalkOnApproval:
    async def test_approval_crosswalks_and_is_visible_through_bridge(
        self, db_session: AsyncSession
    ) -> None:
        # Two foreign-only (eswiki) entities that will share one cross-walked English category.
        qp, qq = "Q000601", "Q000602"
        p = await _ground_foreign_only(db_session, qp)
        q = await _ground_foreign_only(db_session, qq)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

        wikidata = _CrosswalkWikidata(
            entity_sitelinks={
                qp: {"eswiki": "Art P"},
                qq: {"eswiki": "Art Q"},
            },
            category_sitelinks={
                "QC1": {"enwiki": "Category:Shared"},
                "QC2": {"enwiki": "Category:P only"},
                "QC3": {"enwiki": "Category:Q only"},
            },
        )
        fetch_es = _CrosswalkFetch(
            cats={
                "Art P": ["Cat_es:Shared", "Cat_es:P"],
                "Art Q": ["Cat_es:Shared", "Cat_es:Q"],
            },
            cat_qids={
                "Cat_es:Shared": "QC1",
                "Cat_es:P": "QC2",
                "Cat_es:Q": "QC3",
            },
        )
        service = _service(factory, wikidata, {"es": fetch_es})

        await service.enrich_on_approval(p, qp)
        await service.enrich_on_approval(q, qq)

        # Both entities carry cross-walked categories, all in the one Wikipedia namespace (FR-007).
        assert set(await _sources(factory, p)) == {"wikipedia"}
        assert set(await _sources(factory, q)) == {"wikipedia"}

        # Cross-Feature Data Contract (SC-005): read THROUGH the 083 bridge — P neighbors Q via
        # the cross-walked "Shared" category, indistinguishable from a native English category.
        async with factory() as s:
            neighbors = await assign_repo.shared_category_bridge(s, p)
        assert (uuid.UUID(str(q)), "Shared") in {
            (uuid.UUID(str(n.neighbor_id)), n.shared_category) for n in neighbors
        }
        assert all(n.shared_category == "Shared" for n in neighbors)

    async def test_refresh_recovers_categories_and_is_idempotent(
        self, db_session: AsyncSession
    ) -> None:
        # A pre-existing foreign-only entity (multi-language) re-grounded/refreshed: enrich runs
        # again through the same seam and recovers the UNION, with no duplicates on a second pass.
        qid = "Q000603"
        eid = await _ground_foreign_only(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

        wikidata = _CrosswalkWikidata(
            entity_sitelinks={qid: {"eswiki": "Art R", "frwiki": "Article R"}},
            category_sitelinks={
                "QC1": {"enwiki": "Category:Alpha"},
                "QC2": {"enwiki": "Category:Beta"},
            },
        )
        service = _service(
            factory,
            wikidata,
            {
                "es": _CrosswalkFetch(
                    {"Art R": ["Cat_es:Alpha"]}, {"Cat_es:Alpha": "QC1"}
                ),
                "fr": _CrosswalkFetch(
                    {"Article R": ["Cat_fr:Beta"]}, {"Cat_fr:Beta": "QC2"}
                ),
            },
        )

        await service.enrich_on_approval(eid, qid)  # first (approval)
        await service.enrich_on_approval(
            eid, qid
        )  # second (refresh) — must not duplicate

        async with factory() as s:
            names = (
                (
                    await s.execute(
                        select(func.count())
                        .select_from(EntityCategory)
                        .where(EntityCategory.entity_id == eid)
                    )
                ).scalar_one(),
                set(
                    (
                        await s.execute(
                            select(EntityCategory.source).where(
                                EntityCategory.entity_id == eid
                            )
                        )
                    )
                    .scalars()
                    .all()
                ),
            )
        count, sources = names
        assert count == 2  # union {Alpha, Beta} across es+fr, no duplicate on refresh
        assert sources == {"wikipedia"}

    async def test_knowledge_base_failure_leaves_entity_grounded(
        self, db_session: AsyncSession
    ) -> None:
        # The cross-walk's sitelink lookup fails: enrich_on_approval still completes, properties
        # land, and no categories are written (best-effort/non-blocking, FR-011/FR-014).
        qid = "Q000604"
        eid = await _ground_foreign_only(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        wikidata = _CrosswalkWikidata({}, {}, fail_sitelinks=True)
        service = _service(factory, wikidata, {})

        await service.enrich_on_approval(eid, qid)  # must not raise

        async with factory() as s:
            row = (
                await s.execute(select(NamedEntity).where(NamedEntity.id == eid))
            ).scalar_one()
            assert "occupation" in row.properties  # primary enrichment intact
            assert row.external_ids["wikidata"]["id"] == qid
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(EntityCategory)
                    .where(EntityCategory.entity_id == eid)
                )
            ).scalar_one()
        assert n == 0  # no categories written on the failed cross-walk

    async def test_size_fetch_failure_leaves_entity_grounded(
        self, db_session: AsyncSession
    ) -> None:
        # The cross-walk succeeds but the store-side size fetch raises: enrich_on_approval still
        # completes (best-effort) and nothing is half-written (single commit, FR-012/FR-014).
        qid = "Q000605"
        eid = await _ground_foreign_only(db_session, qid)
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        wikidata = _CrosswalkWikidata(
            entity_sitelinks={qid: {"eswiki": "Art S"}},
            category_sitelinks={"QC1": {"enwiki": "Category:Gamma"}},
        )
        service = _service(
            factory,
            wikidata,
            {
                "es": _CrosswalkFetch(
                    {"Art S": ["Cat_es:Gamma"]}, {"Cat_es:Gamma": "QC1"}
                )
            },
            size_factory=_RaisingSizes,
        )

        await service.enrich_on_approval(eid, qid)  # must not raise

        async with factory() as s:
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(EntityCategory)
                    .where(EntityCategory.entity_id == eid)
                )
            ).scalar_one()
            row = (
                await s.execute(select(NamedEntity).where(NamedEntity.id == eid))
            ).scalar_one()
        assert n == 0  # size failure rolled back the add; nothing half-written
        assert "occupation" in row.properties  # primary enrichment intact

    async def test_dbpedia_linked_entity_skips_foreign_fallback(
        self, db_session: AsyncSession
    ) -> None:
        # FR-001 guard: an entity with a stored DBpedia IRI (⇒ has an English article) must NOT be
        # foreign-cross-walked even if the English fetch is omitted this run and foreign sitelinks
        # exist. The default English fetch stub returns nothing (omit), so categorize_entity yields
        # None — but the has_dbpedia_iri guard skips the fallback.
        qid = "Q000606"
        eid = await _ground_with_dbpedia(
            db_session, qid, "http://dbpedia.org/resource/Title_Dbp"
        )
        factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
        # Wikidata WOULD offer foreign sitelinks + a cross-walkable category if the fallback ran.
        wikidata = _CrosswalkWikidata(
            entity_sitelinks={qid: {"eswiki": "Art D"}},
            category_sitelinks={"QC1": {"enwiki": "Category:Delta"}},
        )
        service = _service(
            factory,
            wikidata,
            {
                "es": _CrosswalkFetch(
                    {"Art D": ["Cat_es:Delta"]}, {"Cat_es:Delta": "QC1"}
                )
            },
        )

        await service.enrich_on_approval(eid, qid)

        # The guard skipped the fallback: no foreign-cross-walked categories were added.
        async with factory() as s:
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(EntityCategory)
                    .where(EntityCategory.entity_id == eid)
                )
            ).scalar_one()
        assert n == 0
