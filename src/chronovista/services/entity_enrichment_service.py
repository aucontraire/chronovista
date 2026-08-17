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
human display fields. It is only ever scheduled for a **newly created** grounded entity, whose
``properties`` bag is empty — so the full-replace write is safe and matches what a later batch load
would write (FR-002).

Graceful degradation (FR-006/FR-006a) is added in US2 (``enrich_on_approval`` hardening).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.models.entity_enrichment import ExternalIdentifier
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.dbpedia_resolver import DbpediaResolver
from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable

logger = logging.getLogger(__name__)


class EntityEnrichmentService:
    """Fetch-and-persist curated Wikidata properties (and a DBpedia link) for a grounded entity."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client_factory: Callable[[], WikidataClient] = WikidataClient,
        dbpedia_factory: Callable[[], DbpediaResolver] = DbpediaResolver,
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
        """
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._dbpedia_factory = dbpedia_factory
        self._repo = NamedEntityRepository()

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

        Two independent best-effort steps: the Wikidata **properties** write (primary), then a DBpedia
        **identifier** merge. The DBpedia step is separate on purpose — its public endpoint is
        unreliable, so a DBpedia failure must not affect the properties that already landed.
        """
        entity_present = await self._write_properties(entity_id, qid)
        if entity_present is False:
            return  # entity absent — nothing to attach a DBpedia link to either
        await self._store_dbpedia(entity_id, qid)

    async def _write_properties(self, entity_id: uuid.UUID, qid: str) -> bool | None:
        """Fetch + persist properties. Returns False if the entity is absent, else True/None."""
        try:
            client = self._client_factory()
            properties: dict[str, Any] = await client.fetch_properties(qid)
            async with self._session_factory() as session:
                rowcount = await self._repo.replace_properties(
                    session, entity_id, properties=properties
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
