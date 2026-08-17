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

Degradation-safe (Constitution VIII): DBpedia's public SPARQL endpoint is unreliable, so any transport
error, timeout, or empty result returns ``None`` — the caller simply records no DBpedia link and the
batch pipeline can fill it later. It never raises.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

DBPEDIA_SPARQL = "https://dbpedia.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "chronovista/1.0 (local personal library tooling)"
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

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=self._timeout
        )

    async def resolve(self, qid: str) -> tuple[str, str] | None:
        """Return ``(dbpedia_iri, link_provenance)`` for ``qid``, or ``None`` if none resolves.

        Never raises: an unreachable/flaky DBpedia endpoint or an item with no English Wikipedia
        article both yield ``None`` (the entity keeps no DBpedia link; the pipeline may fill it).
        """
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            # Each step degrades independently: DBpedia's SPARQL is the flaky part, so a SPARQL
            # failure must not skip the (more reliable) enwiki-sitelink fallback.
            try:
                iri = await self._owl_sameas(http, qid)
            except Exception:  # noqa: BLE001
                iri = None
            if iri:
                return iri, PROV_SAMEAS
            try:
                title = await self._enwiki_title(http, qid)
            except Exception:  # noqa: BLE001
                title = None
            if title:
                return self._resource_iri(title), PROV_SITELINK
            return None
        finally:
            if owns:
                await http.aclose()

    async def _owl_sameas(self, http: httpx.AsyncClient, qid: str) -> str | None:
        """The DBpedia resource whose ``owl:sameAs`` is this Wikidata item, if any."""
        query = (
            "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
            "SELECT ?resource WHERE {\n"
            f"  ?resource owl:sameAs <http://www.wikidata.org/entity/{qid}> .\n"
            '  FILTER(STRSTARTS(STR(?resource), "http://dbpedia.org/resource/"))\n'
            "} LIMIT 1"
        )
        resp = await http.post(
            DBPEDIA_SPARQL,
            data={"query": query, "format": "application/sparql-results+json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if bindings:
            value = bindings[0].get("resource", {}).get("value")
            return str(value) if value else None
        return None

    async def _enwiki_title(self, http: httpx.AsyncClient, qid: str) -> str | None:
        """The item's English-Wikipedia article title from its Wikidata sitelink, if any."""
        params: dict[str, Any] = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "sitelinks",
            "sitefilter": "enwiki",
            "format": "json",
        }
        resp = await http.get(WIKIDATA_API, params=params)
        resp.raise_for_status()
        entity = (resp.json().get("entities") or {}).get(qid) or {}
        title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        return str(title) if title else None

    @staticmethod
    def _resource_iri(title: str) -> str:
        """Build the DBpedia resource IRI for a Wikipedia article title (matches the pipeline)."""
        return "http://dbpedia.org/resource/" + urllib.parse.quote(
            title.replace(" ", "_"), safe="()_,'-.!*"
        )
