"""Fetch an entity's Wikipedia categories — the entity→categories direction (Feature 084).

Given Wikipedia article titles, return each one's **non-hidden** category names
(``action=query&prop=categories&clshow=!hidden``). This is a sibling of Feature 083's
``CategorySizeService`` (which goes category→global-size), not a reuse of it: the direction and
response shape differ, so the two services share only the low-level HTTP conventions — the
Wikimedia-compliant contact User-Agent, the timeout, the bounded retry, and the polite
inter-batch pause.

Graceful degradation (Constitution VIII): a title that errors, 404s, or is missing is **omitted**
from the result (the caller leaves the entity as-is and may retry on a later run); a title that
exists but has no non-hidden categories is returned with an **empty list** (processed, zero —
distinct from a fetch failure). The service never raises for a transport/API error.

Name-free: article titles and category names are runtime arguments, never embedded in source.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any

import httpx

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "chronovista/1.0 (https://github.com/aucontraire/chronovista; category coverage fetch)"


def _api_url_for(language: str) -> str:
    """The MediaWiki API endpoint for a language's Wikipedia (``en`` → the default host)."""
    return f"https://{language}.wikipedia.org/w/api.php"


_DEFAULT_TIMEOUT = 15.0
_BATCH = 50  # MediaWiki titles-per-request limit for most query modules
_CLLIMIT = 500  # categories returned per page before a continue token is issued
_MAX_RETRIES = 3
_DEFAULT_PAUSE = (
    1.0  # polite gap (seconds) between batches — Wikimedia rate etiquette (FR-014)
)
# A ≤50-title batch at cllimit=500 drains in a handful of pages for any real article; this cap
# only guards against a server that echoes a non-advancing clcontinue (would otherwise hang).
_MAX_CONTINUATIONS = 50


class EntityCategoryFetchService:
    """Fetch each article's non-hidden Wikipedia category names (best-effort, batched, paced)."""

    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        pause: float = _DEFAULT_PAUSE,
        language: str = "en",
    ) -> None:
        self._timeout = timeout
        self._client_factory = client_factory or self._new_client
        self._pause = pause
        # Which Wikipedia to query. Default "en" preserves every existing caller unchanged;
        # the foreign cross-walk (Feature 100) constructs the service per non-English language.
        self._language = language
        self._api_url = _api_url_for(language)

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=self._timeout
        )

    @staticmethod
    def _norm(title: str) -> str:
        """Normalize a title for matching (MediaWiki maps ``_`` and blanks identically)."""
        return title.replace("_", " ").strip().lower()

    async def categories_for_titles(
        self, titles: Iterable[str]
    ) -> dict[str, list[str]]:
        """Return ``{article title: [non-hidden category names]}`` for titles that resolve.

        Batched (≤50 titles/request) and paced between batches (FR-001, FR-014). Keys are the
        caller's exact input titles, not Wikipedia's canonicalized form. A title that errors/404s
        or is reported missing is **absent** from the result (graceful — retry later); a title
        that exists with no non-hidden categories maps to an **empty list** (processed, zero).
        """
        unique = [t for t in dict.fromkeys(titles) if t]
        out: dict[str, list[str]] = {}
        client = self._client_factory()
        try:
            for batch_index, start in enumerate(range(0, len(unique), _BATCH)):
                if batch_index > 0 and self._pause > 0:
                    await asyncio.sleep(self._pause)  # polite gap between batches
                out.update(
                    await self._fetch_batch(client, unique[start : start + _BATCH])
                )
        finally:
            await client.aclose()
        return out

    async def _fetch_batch(
        self, client: httpx.AsyncClient, batch: list[str]
    ) -> dict[str, list[str]]:
        """Fetch one ≤50-title batch, following ``continue`` tokens until the batch is drained.

        ``prop=categories`` paginates across the whole multi-title query (``cllimit`` bounds the
        page, not each title), so a batch of 50 titles with many categories spans several pages;
        the continue loop accumulates them before returning. The loop is bounded by
        ``_MAX_CONTINUATIONS`` so a server that echoes a non-advancing ``clcontinue`` cannot hang
        the run — it degrades to a partial (append-only, best-effort) result instead.

        ``redirects=1`` is set so a redirect title (e.g. a less-common spelling that points at the
        canonical article) resolves to the article that actually carries the categories; the
        per-page remap of MediaWiki's ``normalized``/``redirects`` hops keeps the result keyed by
        the caller's original input title.
        """
        by_norm = {self._norm(t): t for t in batch}
        accumulated: dict[str, list[str]] = {}
        base: dict[str, str] = {
            "action": "query",
            "format": "json",
            "prop": "categories",
            "clshow": "!hidden",
            "cllimit": str(_CLLIMIT),
            "redirects": "1",  # follow redirect titles to the real article (see below)
            "titles": "|".join(batch),
        }
        cont: dict[str, str] = {}
        for _ in range(_MAX_CONTINUATIONS):
            data = await self._get(client, {**base, **cont})
            query = data.get("query") or {}
            # With redirects=1 a page is keyed by its *resolved* title: a request for the redirect
            # "Old Name" comes back as the article "New Name", whose norm is absent from by_norm.
            # Without remapping, that page fails the by_norm lookup below and the entity is stored
            # as processed-zero forever (the Feature 084 redirect bug). So fold MediaWiki's own
            # normalized→redirect hop chain back onto the caller's original input title. Processing
            # 'normalized' before 'redirects' resolves the (input → canonical → target) chain in
            # order; re-running it each continuation page is idempotent.
            if isinstance(query, dict):
                for hop_key in ("normalized", "redirects"):
                    hops = query.get(hop_key)
                    if not isinstance(hops, list):
                        continue
                    for hop in hops:
                        if not isinstance(hop, dict):
                            continue
                        origin = by_norm.get(self._norm(str(hop.get("from", ""))))
                        if origin is not None:
                            by_norm[self._norm(str(hop.get("to", "")))] = origin
            pages = query.get("pages") or {}
            if isinstance(pages, dict):
                for page in pages.values():
                    if not isinstance(page, dict):
                        continue
                    original = by_norm.get(self._norm(str(page.get("title", ""))))
                    if original is None:
                        continue
                    if "missing" in page or "invalid" in page:
                        continue  # title not found — omit (unresolvable / retry later)
                    # Seen → at least an empty list (processed, zero), distinct from omitted.
                    names = accumulated.setdefault(original, [])
                    for cat in page.get("categories") or []:
                        ct = str(cat.get("title", ""))
                        name = (
                            ct[len("Category:") :] if ct.startswith("Category:") else ct
                        )
                        if name:
                            names.append(name)
            cont_block = data.get("continue")
            if isinstance(cont_block, dict) and "clcontinue" in cont_block:
                cont = {k: str(v) for k, v in cont_block.items()}
                continue
            break
        return accumulated

    async def wikibase_items_for_categories(
        self, category_titles: Iterable[str]
    ) -> dict[str, str]:
        """Map each category page title on THIS language's wiki to its Wikidata item QID.

        Uses ``prop=pageprops&ppprop=wikibase_item`` (the Feature 100 cross-walk's first hop).
        Keys are the caller's exact input titles (e.g. a foreign ``Categoría:…``); a category with
        no Wikidata item is simply absent from the result. Batched ≤50 titles/request and paced
        between batches, the same etiquette as the category fetch (FR-016). Best-effort: a failed
        request yields no mapping for its batch rather than raising (FR-014).
        """
        unique = [t for t in dict.fromkeys(category_titles) if t]
        out: dict[str, str] = {}
        if not unique:
            return out
        client = self._client_factory()
        try:
            for batch_index, start in enumerate(range(0, len(unique), _BATCH)):
                if batch_index > 0 and self._pause > 0:
                    await asyncio.sleep(self._pause)
                batch = unique[start : start + _BATCH]
                by_norm = {self._norm(t): t for t in batch}
                data = await self._get(
                    client,
                    {
                        "action": "query",
                        "format": "json",
                        "prop": "pageprops",
                        "ppprop": "wikibase_item",
                        "titles": "|".join(batch),
                    },
                )
                query = data.get("query") or {}
                if not isinstance(query, dict):
                    continue
                for norm_entry in query.get("normalized") or []:
                    if isinstance(norm_entry, dict):
                        origin = by_norm.get(
                            self._norm(str(norm_entry.get("from", "")))
                        )
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
        finally:
            await client.aclose()
        return out

    async def _get(
        self, client: httpx.AsyncClient, params: dict[str, str]
    ) -> dict[str, Any]:
        """One API call, retrying a transient failure a bounded number of times.

        Returns an empty dict if all attempts fail — the batch then yields no categories for its
        titles, which the caller reads as "omitted / retry later" rather than an error.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.get(self._api_url, params=params)
                resp.raise_for_status()
                parsed = resp.json()
                return dict(parsed) if isinstance(parsed, dict) else {}
            except httpx.HTTPError:
                if attempt == _MAX_RETRIES - 1:
                    return {}
                await asyncio.sleep(min(2**attempt, 5))
        return {}
