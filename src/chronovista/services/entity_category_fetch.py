"""Fetch an entity's Wikipedia categories — the entity→categories direction (Feature 084).

Given Wikipedia article titles, return each one's **non-hidden** category names
(``action=query&prop=categories&clshow=!hidden``). This is a sibling of Feature 083's
``CategorySizeService`` (which goes category→global-size), not a reuse of it: the direction and
response shape differ, so the two services share only the shared :class:`WikimediaTransport`
(Feature 102) — the Wikimedia-compliant contact User-Agent, the per-request client lifecycle, the
unified rate-limit/backoff, the chunking helper, and the single MediaWiki continuation helper
(``paginate_mediawiki``, which owns the continuation loop and the ``normalized``/``redirects``
hop-remap). This service owns only its endpoint, request parameters, and response parsing (FR-009).

Graceful degradation (Constitution VIII): a title is **omitted** from the result only when its
batch was UNREACHABLE — the transport raised ``WikidataUnavailable`` (a transport/parse failure, an
error-object-in-200, or an incomplete continuation) and this service **absorbs** it per the spec's
per-service table, dropping that batch's titles for a later retry (FR-008). A title that is reached
but has no non-hidden categories — including one Wikipedia reports ``missing``/``invalid`` — is
returned with an **empty list** (reached/settled, zero), distinct from the omit-on-unreachable case.
So an absent title means "retry later" and a present-empty title means "reached, nothing there" (the
distinction the operator-facing batch report surfaces — FR-017).

Name-free: article titles and category names are runtime arguments, never embedded in source.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from chronovista.services.wikimedia_transport import (
    WikidataUnavailable,
    WikimediaTransport,
)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
# The per-client component label baked into the single-sourced outbound User-Agent (G1/FR-002):
# the transport assembles the compliant UA from this label; no UA string is hand-built here.
_UA_COMPONENT = "category coverage fetch"


def _api_url_for(language: str) -> str:
    """The MediaWiki API endpoint for a language's Wikipedia (``en`` → the default host)."""
    return f"https://{language}.wikipedia.org/w/api.php"


_DEFAULT_TIMEOUT = 15.0
_CLLIMIT = 500  # categories returned per page before a continue token is issued
_DEFAULT_PAUSE = (
    1.0  # polite gap (seconds) between batches — Wikimedia rate etiquette (FR-014)
)
# A ≤50-title batch at cllimit=500 drains in a handful of pages for any real article; this cap
# only guards against a server that echoes a non-advancing continuation token (would otherwise
# hang). It
# is passed to the transport's paginate_mediawiki as max_pages: exceeding it raises an explicit
# incomplete signal (never a silently truncated prefix presented as complete — SC-004).
_MAX_CONTINUATIONS = 50


class EntityCategoryFetchService:
    """Fetch each article's non-hidden Wikipedia category names (best-effort, batched, paced)."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        pause: float = _DEFAULT_PAUSE,
        language: str = "en",
    ) -> None:
        self._http = http
        self._timeout = timeout
        self._pause = pause
        # Which Wikipedia to query. Default "en" preserves every existing caller unchanged;
        # the foreign cross-walk (Feature 100) constructs the service per non-English language.
        self._language = language
        self._api_url = _api_url_for(language)

    def _transport(self) -> WikimediaTransport:
        """The shared outbound transport for this service (FR-001).

        Preserves the ``http=None`` injection seam: a per-request client by default, or the injected
        client reused when one is supplied (tests/DI). UA assembly, the unified retry/backoff, the
        unreachable-vs-empty contract, chunking, and the continuation handling all live in the
        transport.
        """
        return WikimediaTransport(_UA_COMPONENT, http=self._http, timeout=self._timeout)

    @staticmethod
    def _norm(title: str) -> str:
        """Normalize a title for matching (MediaWiki maps ``_`` and blanks identically)."""
        return title.replace("_", " ").strip().lower()

    async def categories_for_titles(
        self, titles: Iterable[str]
    ) -> dict[str, list[str]]:
        """Return ``{article title: [non-hidden category names]}`` for titles that resolve.

        Batched (≤50 titles/request) and paced between batches (FR-001, FR-014). Keys are the
        caller's exact input titles, not Wikipedia's canonicalized form. A title is **absent** from
        the result only when its batch was unreachable (the transport raised and this service
        absorbed it — retry later); a reached title maps to a list, which is **empty** when the
        article has no non-hidden categories OR is reported missing/invalid (reached/settled, zero —
        not a failure).
        """
        unique = [t for t in dict.fromkeys(titles) if t]
        out: dict[str, list[str]] = {}
        transport = self._transport()
        for batch_index, batch in enumerate(WikimediaTransport.chunk(unique)):
            if batch_index > 0 and self._pause > 0:
                await asyncio.sleep(self._pause)  # polite gap between batches
            out.update(await self._fetch_batch(transport, batch))
        return out

    async def _fetch_batch(
        self, transport: WikimediaTransport, batch: list[str]
    ) -> dict[str, list[str]]:
        """Fetch one ≤50-title batch via the shared MediaWiki continuation helper.

        ``prop=categories`` paginates across the whole multi-title query (``cllimit`` bounds the
        page, not each title), so a batch of 50 titles with many categories spans several pages;
        ``paginate_mediawiki`` follows the continuation tokens, merges each page's category list,
        and re-attributes MediaWiki's ``normalized``/``redirects`` hops back to the caller's
        original input titles (the v0.104.1 false-zero fix) — so a redirect title (e.g. a
        less-common spelling that points at the canonical article) still resolves to the article
        that carries the categories, keyed by the caller's original input.

        The transport **raises** :class:`WikidataUnavailable` on a transport/parse failure in any
        page OR when the continuation exceeds ``_MAX_CONTINUATIONS`` (an explicit incomplete
        signal, not a silently truncated prefix). This service **absorbs** it per the spec's
        per-service table: the batch's titles are omitted from the result (a retry-later signal),
        exactly the omit-on-failure degrade the hand-rolled loop produced before.
        """
        base: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "prop": "categories",
            "clshow": "!hidden",
            "cllimit": str(_CLLIMIT),
            "redirects": "1",  # follow redirect titles to the real article (hop-remap below)
            "titles": "|".join(batch),
        }
        try:
            pages = await transport.paginate_mediawiki(
                self._api_url,
                params=base,
                max_pages=_MAX_CONTINUATIONS,
            )
        except WikidataUnavailable:
            # Unreachable OR incomplete (exceeded max_pages) → omit this batch's titles (retry
            # later). Never a partial set presented as complete, never a false "processed-zero".
            return {}
        result: dict[str, list[str]] = {}
        for original, page in pages.items():
            # Seen → at least an empty list (processed, zero), distinct from an omitted title.
            names: list[str] = []
            for cat in page.get("categories") or []:
                ct = str(cat.get("title", ""))
                name = ct[len("Category:") :] if ct.startswith("Category:") else ct
                if name:
                    names.append(name)
            result[original] = names
        return result

    async def wikibase_items_for_categories(
        self, category_titles: Iterable[str]
    ) -> dict[str, str]:
        """Map each category page title on THIS language's wiki to its Wikidata item QID.

        Uses ``prop=pageprops&ppprop=wikibase_item`` (the Feature 100 cross-walk's first hop).
        Keys are the caller's exact input titles (e.g. a foreign ``Categoría:…``); a category with
        no Wikidata item is simply absent from the result. Batched ≤50 titles/request and paced
        between batches, the same etiquette as the category fetch (FR-016). Best-effort: an
        unreachable batch yields no mapping for its titles rather than raising (FR-014) — the
        transport's ``WikidataUnavailable`` is absorbed here.
        """
        unique = [t for t in dict.fromkeys(category_titles) if t]
        out: dict[str, str] = {}
        if not unique:
            return out
        transport = self._transport()
        for batch_index, batch in enumerate(WikimediaTransport.chunk(unique)):
            if batch_index > 0 and self._pause > 0:
                await asyncio.sleep(self._pause)
            by_norm = {self._norm(t): t for t in batch}
            try:
                data = await transport.get_json(
                    self._api_url,
                    params={
                        "action": "query",
                        "format": "json",
                        "prop": "pageprops",
                        "ppprop": "wikibase_item",
                        "titles": "|".join(batch),
                    },
                )
            except WikidataUnavailable:
                continue  # unreachable batch → no mapping for its titles (retry later)
            query = data.get("query") or {}
            if not isinstance(query, dict):
                continue
            for norm_entry in query.get("normalized") or []:
                if isinstance(norm_entry, dict):
                    origin = by_norm.get(self._norm(str(norm_entry.get("from", ""))))
                    if origin is not None:
                        by_norm[self._norm(str(norm_entry.get("to", "")))] = origin
            pages = query.get("pages") or {}
            if not isinstance(pages, dict):
                continue
            for page in pages.values():
                if not isinstance(page, dict):
                    continue
                original = by_norm.get(self._norm(str(page.get("title", ""))))
                if original is None:
                    continue
                qid = (page.get("pageprops") or {}).get("wikibase_item")
                if isinstance(qid, str) and qid:
                    out[original] = qid
        return out
