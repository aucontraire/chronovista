"""
DBpedia identifier resolution for on-approval enrichment (Feature: on-approval DBpedia).

Resolves a grounded entity's Wikidata QID to its **DBpedia resource IRI** — the identifier link
the entity detail page renders. Ported from the gitignored ``scripts/entity_resolution/fetch_dbpedia.py``
so shipped code no longer depends on an untracked file.

Resolution is **by QID, never by name** (so a Wikidata label that differs from the Wikipedia article
title does not matter):

1. **owl:sameAs** — a SPARQL query to DBpedia asking which ``dbpedia.org/resource/*`` IRI is
   ``owl:sameAs`` the Wikidata item. This is an identifier join.
2. **enwiki sitelink fallback** — when ``owl:sameAs`` returns nothing (it goes stale as Wikidata
   merges items), read the item's English-Wikipedia sitelink from Wikidata and build the DBpedia IRI
   from that article title. Still an identifier lookup — the sitelink is Wikidata's own statement
   about which article describes the item.

Only the **IRI** (identifier) is resolved here — not DBpedia's category/abstract content, which stays
deferred (ADR-010). This mirrors exactly what the batch pipeline's load writes into
``external_ids.dbpedia``.

Degradation-safe (Constitution VIII): DBpedia's public SPARQL endpoint is unreliable. Both external
calls now go through the shared :class:`WikimediaTransport` (Feature 102), which retries transient
failures (timeout/reset, 429, 5xx) within a bounded budget before giving up — the only retry this
one-shot, detached enrichment path ever gets, since no scheduled batch sweeper exists (FR-016). On
exhaustion the resolver **absorbs** the transport's ``WikidataUnavailable`` and keeps its contract:
``resolve()`` returns ``None`` and never raises. The unreachable-vs-genuinely-absent distinction the
``None`` return would otherwise discard is recorded as a WARNING log here (FR-006/FR-015), so a
transient DBpedia outage is observable rather than silently read as "no DBpedia link". A genuine
no-match stays a quiet ``None``.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from chronovista.services.wikimedia_transport import (
    WikidataUnavailable,
    WikimediaTransport,
)

logger = logging.getLogger(__name__)

DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# The per-client component label baked into the single-sourced outbound User-Agent (G1/FR-002):
# the transport assembles the UA from this label; no UA string is hand-built here.
_UA_COMPONENT = "dbpedia/sitelink resolver"
_DEFAULT_TIMEOUT = 8.0

# Provenance labels stored in the identifier's link_provenance (backend-only; not rendered).
PROV_SAMEAS = "owl:sameAs from wikidata"
PROV_SITELINK = "enwiki sitelink"


class DbpediaResolver:
    """Resolve a Wikidata QID to its DBpedia resource IRI (identifier only)."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._http = http
        self._timeout = timeout

    def _transport(self) -> WikimediaTransport:
        """The shared outbound transport for this resolver (FR-001).

        Preserves the ``http=None`` injection seam: a per-request client by default, or the injected
        client reused when one is supplied (tests/DI). UA assembly, the unified retry/backoff, and
        the unreachable-vs-empty contract all live in the transport.
        """
        return WikimediaTransport(_UA_COMPONENT, http=self._http, timeout=self._timeout)

    async def resolve(self, qid: str) -> tuple[str, str] | None:
        """Return ``(dbpedia_iri, link_provenance)`` for ``qid``, or ``None`` if none resolves.

        Never raises: an unreachable/flaky DBpedia endpoint or an item with no English Wikipedia
        article both yield ``None``. The two cases are distinguished in the log — an unreachable
        outcome (the transport exhausted its retries) is recorded at WARNING so a transient outage
        is observable, while a genuine no-match stays a quiet ``None``. In neither case is a
        confirmed absence persisted; the entity stays eligible for a later reground (FR-006/FR-015).
        """
        transport = self._transport()
        # Each step degrades independently: DBpedia's SPARQL is the flaky part, so a SPARQL
        # failure must not skip the (more reliable) enwiki-sitelink fallback. The transport has
        # already retried each call within its bounded budget; a WikidataUnavailable here means
        # the step was unreachable (not that the source confirmed an absence).
        unreachable = False
        try:
            iri = await self._owl_sameas(transport, qid)
        except WikidataUnavailable:
            unreachable = True
            iri = None
        if iri:
            return iri, PROV_SAMEAS
        try:
            title = await self._enwiki_title(transport, qid)
        except WikidataUnavailable:
            unreachable = True
            title = None
        if title:
            return self._resource_iri(title), PROV_SITELINK
        if unreachable:
            # Record the distinction the `None` return discards (FR-006): this was a transient
            # upstream failure, NOT a verified "no DBpedia link". No downstream consumer acts on
            # it (the caller skips-and-moves-on), so a log line is the right home.
            logger.warning(
                "DBpedia resolution for qid=%s was UNREACHABLE after bounded retries "
                "(transient upstream failure) — no link recorded; this is NOT a confirmed "
                "absence and the entity stays eligible for a later reground",
                qid,
            )
        return None

    async def _owl_sameas(self, transport: WikimediaTransport, qid: str) -> str | None:
        """The DBpedia resource whose ``owl:sameAs`` is this Wikidata item, if any."""
        query = (
            "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
            "SELECT ?resource WHERE {\n"
            f"  ?resource owl:sameAs <http://www.wikidata.org/entity/{qid}> .\n"
            '  FILTER(STRSTARTS(STR(?resource), "http://dbpedia.org/resource/"))\n'
            "} LIMIT 1"
        )
        data = await transport.post_form(
            DBPEDIA_SPARQL,
            data={"query": query, "format": "application/sparql-results+json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        # Total parse: the transport only guarantees ``data`` is a dict with no ``error`` key, so a
        # structurally-odd-but-JSON-valid 200 body (``{"results": null}``, a non-list ``bindings``)
        # must read as "no match" (None), never raise — the resolver's "Never raises" contract.
        results = data.get("results")
        if not isinstance(results, dict):
            return None
        bindings = results.get("bindings")
        if not isinstance(bindings, list) or not bindings:
            return None
        first = bindings[0]
        if not isinstance(first, dict):
            return None
        resource = first.get("resource")
        if not isinstance(resource, dict):
            return None
        value = resource.get("value")
        return str(value) if value else None

    async def _enwiki_title(
        self, transport: WikimediaTransport, qid: str
    ) -> str | None:
        """The item's English-Wikipedia article title from its Wikidata sitelink, if any."""
        params: dict[str, Any] = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": "enwiki",
            "format": "json",
        }
        data = await transport.get_json(WIKIDATA_API, params=params)
        # Total parse (same contract as _owl_sameas): a structurally-odd-but-JSON-valid 200 body
        # (``{"entities": null}``, ``sitelinks`` not a dict) reads as "no article" (None), never
        # raises — type-guard each structural access.
        entities = data.get("entities")
        if not isinstance(entities, dict):
            return None
        entity = entities.get(qid)
        if not isinstance(entity, dict):
            return None
        sitelinks = entity.get("sitelinks")
        if not isinstance(sitelinks, dict):
            return None
        enwiki = sitelinks.get("enwiki")
        if not isinstance(enwiki, dict):
            return None
        title = enwiki.get("title")
        return str(title) if title else None

    @staticmethod
    def _resource_iri(title: str) -> str:
        """Build the DBpedia resource IRI for a Wikipedia article title (matches the pipeline)."""
        return "http://dbpedia.org/resource/" + urllib.parse.quote(
            title.replace(" ", "_"), safe="()_,'-.!*"
        )
