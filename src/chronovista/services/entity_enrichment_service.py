"""
Entity enrichment service (Feature 068, US1).

Fetches an entity's curated Wikidata properties **on approval** and persists them, so a freshly
grounded entity is immediately as rich as a batch-imported one. Runs off the request path: the
create/classify endpoints schedule ``enrich_on_approval`` as a detached ``asyncio.create_task`` after
they commit (research D1), so the create action never waits on Wikidata (SC-003 / FR-005).

The service opens its **own** database session via an injected ``async_sessionmaker`` — the
request-scoped session is closed once the response is returned, so the background job must not reuse
it. This mirrors ``EntityMentionScanService``. The Wikidata client is obtained through an injectable
factory so tests can supply a ``MockTransport``-backed client (Constitution VI — no live external
calls in tests).

The write is **properties-only** (``NamedEntityRepository.replace_properties``): it never touches the
verified ``external_ids`` the endpoint set at create (the anti-clobber guard, research D4) nor the
human display fields. It is scheduled both for a newly created grounded entity (empty bag) AND for a
Feature-073 **refresh** of an existing entity, so the write **merges by source**
(``wikidata_properties.merge_wikidata_blocks``): it fully replaces the Wikidata-sourced blocks while
preserving blocks from other sources (e.g. a DBpedia ``category``). At create time the bag is empty,
so the merge equals the fresh fetch and matches what a later batch load would write (FR-002).

Graceful degradation (FR-006/FR-006a) is added in US2 (``enrich_on_approval`` hardening).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.models.entity_enrichment import ExternalIdentifier
from chronovista.models.wikipedia_image import FallbackOutcome
from chronovista.repositories.entity_category_repository import (
    EntityCategoryRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.wikipedia_category_repository import (
    WikipediaCategoryRepository,
)
from chronovista.services import wikidata_properties as wp
from chronovista.services.category_coverage import (
    WIKIPEDIA_SOURCE,
    categorize_entity,
    default_fetch_factory,
    resolve_and_crosswalk_entity,
    store_categories_for_entity,
)
from chronovista.services.category_size import CategorySizeService
from chronovista.services.dbpedia_resolver import DbpediaResolver
from chronovista.services.entity_category_fetch import EntityCategoryFetchService
from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable
from chronovista.services.wikipedia_image_fallback import WikipediaImageFallback

logger = logging.getLogger(__name__)


def _has_usable_automated_image(properties: dict[str, Any] | None) -> bool:
    """True when ``properties.image.values[0]`` is a non-empty string (a usable automated image).

    Mirrors the resolver's and the Feature 093 candidate query's definition of "has an image": a
    Wikidata P18 block or a prior Wikipedia block both satisfy it. A manually-uploaded image lives in
    a dedicated column (Feature 092), NOT in ``properties``, so it does not satisfy this and does not
    suppress the Wikipedia fallback (Feature 094, FR-001).
    """
    if not isinstance(properties, dict):
        return False
    block = properties.get("image")
    if not isinstance(block, dict):
        return False
    values = block.get("values")
    return (
        isinstance(values, list)
        and len(values) > 0
        and isinstance(values[0], str)
        and bool(values[0])
    )


class EntityEnrichmentService:
    """Fetch-and-persist curated Wikidata properties (and a DBpedia link) for a grounded entity."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client_factory: Callable[[], WikidataClient] = WikidataClient,
        dbpedia_factory: Callable[[], DbpediaResolver] = DbpediaResolver,
        category_fetch_factory: Callable[
            [], EntityCategoryFetchService
        ] = EntityCategoryFetchService,
        size_factory: Callable[[], CategorySizeService] = CategorySizeService,
        image_fallback_factory: Callable[
            [], WikipediaImageFallback
        ] = WikipediaImageFallback,
        crosswalk_fetch_factory: Callable[
            [str], EntityCategoryFetchService
        ] = default_fetch_factory,
    ) -> None:
        """Initialise the service.

        Parameters
        ----------
        session_factory : async_sessionmaker[AsyncSession]
            Factory for the service's own background session (NOT the request session).
        client_factory : Callable[[], WikidataClient]
            Returns a Wikidata client. Overridable in tests with a ``MockTransport``-backed client.
        dbpedia_factory : Callable[[], DbpediaResolver]
            Returns a DBpedia resolver. Overridable in tests.
        category_fetch_factory : Callable[[], EntityCategoryFetchService]
            Returns the entity→categories fetch service (Feature 084). Overridable in tests.
        size_factory : Callable[[], CategorySizeService]
            Returns the category global-size service (Feature 083). Overridable in tests.
        image_fallback_factory : Callable[[], WikipediaImageFallback]
            Returns the Wikipedia free-Commons image fallback (Feature 093/094). Overridable in
            tests with a ``MockTransport``-backed instance.
        """
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._dbpedia_factory = dbpedia_factory
        self._category_fetch_factory = category_fetch_factory
        self._size_factory = size_factory
        self._image_fallback_factory = image_fallback_factory
        self._crosswalk_fetch_factory = crosswalk_fetch_factory
        self._repo = NamedEntityRepository()
        self._cat_repo = WikipediaCategoryRepository()
        self._assign_repo = EntityCategoryRepository()

    async def enrich_on_approval(
        self, entity_id: uuid.UUID, qid: str, source: str = "wikidata"
    ) -> None:
        """Fetch ``qid``'s curated properties and persist them onto ``entity_id`` (properties-only).

        Intended to run detached, after the create/classify commit, for a newly grounded entity
        whose ``properties`` bag is empty. Opens its own session and commits.

        Parameters
        ----------
        entity_id : uuid.UUID
            The just-created grounded entity.
        qid : str
            The approved Wikidata QID whose properties to fetch.
        source : str
            The knowledge-base source (only ``"wikidata"`` is fetched here).

        Notes
        -----
        Runs detached, so it **never raises** (FR-006): a fetch failure or any unexpected error is
        caught and logged at warning level with the entity id + reason (FR-006a), leaving the entity
        grounded and its properties to be filled by the next batch run. The done-callback that retires
        the task handle must therefore never need to inspect an exception.

        Four independent best-effort steps: the Wikidata **properties** write (primary), then the
        Wikipedia **image** fallback (Feature 094 — fills the automated image from a free Commons
        image when the write produced no usable image), a DBpedia **identifier** merge, and the
        Wikipedia **category** fetch (Feature 084). Each secondary step is separate on purpose — its
        external endpoint is unreliable, so its failure must not affect what already landed. The
        category step is add-only (FR-004).
        """
        entity_present = await self._write_properties(entity_id, qid)
        if entity_present is not True:
            # Entity absent (False), or the primary properties fetch failed (None): skip the two
            # secondary best-effort steps. They enrich an entity we have just confirmed and
            # written; on a failed/absent run a later batch retries all three. This also keeps the
            # invariant that a fetch failure opens no further DB sessions.
            return
        await self._store_wikipedia_image(entity_id, qid)
        await self._store_dbpedia(entity_id, qid)
        await self._store_categories(entity_id, qid)

    async def _write_properties(self, entity_id: uuid.UUID, qid: str) -> bool | None:
        """Fetch + persist properties. Returns False if the entity is absent, else True/None."""
        try:
            client = self._client_factory()
            properties: dict[str, Any] = await client.fetch_properties(qid)
            async with self._session_factory() as session:
                # Merge-by-source, not full-replace: this path also runs on a "refresh" of an
                # existing entity (Feature 073), whose bag may hold non-Wikidata blocks (e.g. a
                # DBpedia `category`). Replacing outright wiped those (data loss). merge_wikidata_blocks
                # fully replaces the Wikidata-sourced blocks while preserving every other source. At
                # create time the bag is empty, so the merge equals the fresh fetch (unchanged).
                existing = await self._repo.get(session, entity_id)
                if existing is None:
                    logger.warning(
                        "on-approval enrichment matched no row for entity %s "
                        "(qid=%s) — nothing written",
                        entity_id,
                        qid,
                    )
                    return False
                merged = wp.merge_wikidata_blocks(existing.properties or {}, properties)
                rowcount = await self._repo.replace_properties(
                    session, entity_id, properties=merged
                )
                if rowcount == 0:
                    logger.warning(
                        "on-approval enrichment matched no row for entity %s "
                        "(qid=%s) — nothing written",
                        entity_id,
                        qid,
                    )
                    return False
                await session.commit()
                return True
        except WikidataUnavailable as exc:
            logger.warning(
                "on-approval enrichment could not reach the knowledge base for "
                "entity %s (qid=%s): %s — the entity stays grounded; the next batch "
                "run will fill properties",
                entity_id,
                qid,
                exc,
            )
        except Exception as exc:  # noqa: BLE001 (detached task must not surface)
            logger.warning(
                "on-approval enrichment failed for entity %s (qid=%s): %s",
                entity_id,
                qid,
                exc,
            )
        return None

    async def _store_dbpedia(self, entity_id: uuid.UUID, qid: str) -> None:
        """Best-effort: resolve the DBpedia IRI for ``qid`` and merge it into ``external_ids``.

        Never raises and never disturbs the verified Wikidata identifier (the write is a JSONB merge,
        not a replace). A flaky/unreachable DBpedia endpoint, or an item with no English Wikipedia
        article, simply leaves no DBpedia link — the batch pipeline can fill it later.
        """
        try:
            link = await self._dbpedia_factory().resolve(qid)
            if link is None:
                return
            iri, provenance = link
            identifier = ExternalIdentifier(
                id=iri,
                verified=False,
                status="confirmed",
                link_provenance=provenance,
            ).model_dump()
            async with self._session_factory() as session:
                await self._repo.add_external_id(
                    session, entity_id, source="dbpedia", identifier=identifier
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 (detached task must not surface)
            logger.warning(
                "on-approval DBpedia resolution failed for entity %s (qid=%s): %s",
                entity_id,
                qid,
                exc,
            )

    async def _store_categories(self, entity_id: uuid.UUID, qid: str) -> None:
        """Best-effort (Feature 084): fetch the entity's Wikipedia categories and record them.

        Runs after ``_store_dbpedia`` so it can reuse the DBpedia IRI just stored (the article
        title is derived from it; a QID→title fallback covers entities without one). Uses the same
        shared ``categorize_entity`` pipeline the backfill batch uses — never a parallel path
        (FR-003).

        **Add-only** (``replace=False``): it only ever adds assignments (ON CONFLICT DO NOTHING),
        so for an already-categorized entity it is effectively a no-op and it never deletes or
        replaces an entity's existing categories — only the batch's 373 path does that (FR-004).

        Never raises and never blocks the entity's creation/grounding or its other enrichment: any
        failure (no resolvable article, a fetch error, a DB error) is caught and logged, leaving the
        entity grounded and its categories to be filled by a later batch run.

        Foreign-only fallback (Feature 100): when the English path resolves no article AND no stored
        DBpedia IRI is present (a DBpedia IRI implies an English article — out of scope, FR-001), the
        entity's foreign-language categories are cross-walked to English via
        ``resolve_and_crosswalk_entity`` and stored under the same ``wikipedia`` source. Because this
        seam also runs on a Feature-073 reground/refresh, the detail-view Refresh recovers foreign-only
        entities too. The cross-walk and its size fetch run with NO DB session held (the 094 deadlock
        lesson); a short write session persists the single add-only result.
        """
        try:
            resolved_title: str | None = None
            has_dbpedia_iri = False
            async with self._session_factory() as session:
                existing = await self._repo.get(session, entity_id)
                if existing is None:
                    return
                external_ids = existing.external_ids or {}
                dbpedia = external_ids.get("dbpedia")
                has_dbpedia_iri = isinstance(dbpedia, dict) and bool(dbpedia.get("id"))
                resolved_title = await categorize_entity(
                    session,
                    entity_id,
                    qid,
                    external_ids,
                    fetch_service=self._category_fetch_factory(),
                    resolver=self._dbpedia_factory(),
                    cat_repo=self._cat_repo,
                    assign_repo=self._assign_repo,
                    size_service=self._size_factory(),
                    replace=False,
                )
                await session.commit()
            if resolved_title is not None or has_dbpedia_iri:
                # Either the English path handled it, OR a stored DBpedia IRI means the entity HAS
                # an English article (DBpedia is English-Wikipedia-derived) and is out of scope for
                # the foreign cross-walk (FR-001) — even if the English fetch merely failed this
                # run, retry the English path later rather than mis-source foreign categories.
                return

            # Foreign-only fallback (Feature 100): no English article resolved. Cross-walk the
            # entity's foreign-language categories to English. ALL network (sitelinks, per-language
            # category fetch, cross-walk lookups, and the size fetch) runs with NO DB session held
            # — the 094 deadlock lesson — then a short write session persists the result. The
            # cross-walk's own eligibility gate re-confirms there is no enwiki article, so an entity
            # whose English fetch merely failed transiently is correctly skipped here, not mis-filed.
            result = await resolve_and_crosswalk_entity(
                qid,
                wikidata_client=self._client_factory(),
                fetch_factory=self._crosswalk_fetch_factory,
            )
            if result is None or not result.english_categories:
                return  # not eligible, or recovered zero — leave for a later run
            sizes = await self._size_factory().sizes_for(result.english_categories)
            async with self._session_factory() as session:
                if await self._repo.get(session, entity_id) is None:
                    return
                await store_categories_for_entity(
                    session,
                    entity_id,
                    result.english_categories,
                    cat_repo=self._cat_repo,
                    assign_repo=self._assign_repo,
                    sizes=sizes,
                    replace=False,
                    source=WIKIPEDIA_SOURCE,
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 (detached task must not surface)
            logger.warning(
                "on-approval category enrichment failed for entity %s (qid=%s): %s",
                entity_id,
                qid,
                exc,
            )

    async def _store_wikipedia_image(self, entity_id: uuid.UUID, qid: str) -> None:
        """Best-effort (Feature 094): fill the automated image from a free Commons Wikipedia image.

        Runs after the Wikidata property write. SKIPS when the entity already has a usable automated
        image (``properties.image.values[0]`` non-empty) — a Wikidata P18 the property write just
        stored already satisfies this, so a real P18 always wins (FR-001/FR-004), and a re-run on an
        already-imaged entity is a no-op. A manually-uploaded image (a dedicated column, Feature 092)
        does NOT count and does NOT suppress the fetch, so the automated slot is filled for the
        manual/automated toggle (FR-001, clarified). Reuses the Feature 093 gate + writer verbatim;
        only a confirmed free Commons image is stored (FR-002/FR-003).

        Never raises and never blocks the grounding/refresh: any failure (a flaky Wikimedia source, an
        exhausted retry, a DB error) is caught and logged, leaving the Wikidata enrichment intact
        (FR-005). A successful store is logged for operator auditability (FR-010).

        The up-to-3 Wikimedia calls are made with **no DB session open** — mirroring
        ``_store_dbpedia``, not ``_store_categories``. A short read session decides whether to fetch
        (and closes), then the network call runs session-less, then a short write session persists.
        This matters beyond connection-pool hygiene: as a detached task, this coroutine can be
        cancelled at any ``await``; holding a session across the (possibly slow/hung) Wikimedia call
        would leave an ``idle in transaction`` connection on cancellation, deadlocking any later
        ``DROP``/DDL on ``named_entities``/``entity_mentions`` — which is exactly what broke the
        integration suite before this was split.
        """
        try:
            # 1. Short read session: decide whether to fetch at all, then release the connection.
            async with self._session_factory() as session:
                existing = await self._repo.get(session, entity_id)
                if existing is None:
                    return
                if _has_usable_automated_image(existing.properties):
                    # A usable automated image (incl. a just-written P18, or a prior Wikipedia
                    # block on a refresh) is already present — skip (FR-001, FR-004).
                    return

            # 2. Network call with NO DB session held (the crux — see docstring).
            result = await self._image_fallback_factory().evaluate(entity_id, qid)
            if result.outcome is not FallbackOutcome.STORED or not result.filename:
                return

            # 3. Short write session: re-read (a P18 may have landed meanwhile → re-check skip),
            #    then merge the Wikipedia block into the current bag and persist.
            async with self._session_factory() as session:
                existing = await self._repo.get(session, entity_id)
                if existing is None or _has_usable_automated_image(existing.properties):
                    return
                merged = {
                    **(existing.properties or {}),
                    "image": wp.wikipedia_image_block(
                        result.filename, datetime.now(UTC).isoformat()
                    ),
                }
                await self._repo.replace_properties(
                    session, entity_id, properties=merged
                )
                await session.commit()
                logger.info(
                    "on-approval Wikipedia image stored for entity %s (qid=%s): %s",
                    entity_id,
                    qid,
                    result.filename,
                )
        except Exception as exc:  # noqa: BLE001 (detached task must not surface)
            logger.warning(
                "on-approval Wikipedia image fallback failed for entity %s (qid=%s): %s",
                entity_id,
                qid,
                exc,
            )


_enrichment_service: EntityEnrichmentService | None = None


def get_enrichment_service() -> EntityEnrichmentService:
    """Return the module-level ``EntityEnrichmentService`` singleton (FastAPI dependency).

    Lazily initialised with ``db_manager``'s session factory so the DB is configured by first use
    (mirrors ``_get_scan_service``). Used via ``Depends`` in the create/classify endpoints so tests
    can override it (``app.dependency_overrides``) with a fake-client + integration-session service.
    """
    global _enrichment_service
    if _enrichment_service is None:
        from chronovista.config.database import db_manager

        _enrichment_service = EntityEnrichmentService(db_manager.get_session_factory())
    return _enrichment_service
