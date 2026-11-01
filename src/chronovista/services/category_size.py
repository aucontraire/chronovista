"""Fetch Wikipedia category global sizes (Feature 083, roadmap item ①).

A category's *specificity* is measured by its Wikipedia-wide member count — a stable property of
the category, unlike local library membership which drifts as the library grows. This service
reads that count from the live English Wikipedia API (``prop=categoryinfo``), batched, over the
shared :class:`WikimediaTransport` (Feature 102): the transport owns the Wikimedia-compliant
contact User-Agent, the per-request client lifecycle, the unified rate-limit/backoff, and the
unreachable-vs-empty contract; this service owns only the endpoint, the request parameters, and the
response parsing (FR-009).

It is **name-free**: category names are runtime arguments, never embedded in source. (A gitignored
reference implementation lives under ``scripts/entity_resolution/``; that tree carries real entity
names and cannot be imported by tracked code, so this is the tracked, importable version — see the
feature's research notes.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import httpx

from chronovista.services.wikimedia_transport import (
    WikidataUnavailable,
    WikimediaTransport,
)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
# The per-client component label baked into the single-sourced outbound User-Agent (G1/FR-002):
# the transport assembles the compliant UA from this label; no UA string is hand-built here.
_UA_COMPONENT = "category-size fetch"
_DEFAULT_TIMEOUT = 15.0
_DEFAULT_PAUSE = 1.0  # polite gap (seconds) between batches — Wikimedia rate etiquette


class CategorySizeService:
    """Fetches Wikipedia-wide member counts for categories (best-effort)."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        pause: float = _DEFAULT_PAUSE,
    ) -> None:
        self._http = http
        self._timeout = timeout
        self._pause = pause

    def _transport(self) -> WikimediaTransport:
        """The shared outbound transport for this service (FR-001).

        Preserves the ``http=None`` injection seam: a per-request client by default, or the injected
        client reused when one is supplied (tests/DI). UA assembly, the unified retry/backoff, and
        the unreachable-vs-empty contract all live in the transport.
        """
        return WikimediaTransport(_UA_COMPONENT, http=self._http, timeout=self._timeout)

    @staticmethod
    def _norm(name: str) -> str:
        """Normalize a category name for matching (MediaWiki maps ``_`` and blanks identically)."""
        return name.replace("_", " ").strip().lower()

    async def sizes_for(self, names: Iterable[str]) -> dict[str, int]:
        """Return ``{category name: global member count}`` for the names that resolve.

        Names that error, 404, or carry no ``categoryinfo`` are omitted — the caller stores NULL
        and may retry later (graceful degradation). Keys in the result are the caller's exact input
        names (not Wikipedia's canonicalized form).
        """
        unique = list(dict.fromkeys(names))
        out: dict[str, int] = {}
        transport = self._transport()
        for batch_index, batch in enumerate(WikimediaTransport.chunk(unique)):
            if batch_index > 0 and self._pause > 0:
                await asyncio.sleep(self._pause)  # polite gap between batches
            out.update(await self._fetch_batch(transport, batch))
        return out

    async def _fetch_batch(
        self, transport: WikimediaTransport, batch: list[str]
    ) -> dict[str, int]:
        """Fetch one batch's ``categoryinfo`` sizes, absorbing an unreachable batch as omitted.

        The transport raises :class:`WikidataUnavailable` on transport failure, exhausted retries,
        a non-JSON/non-object 200 body, or an API-error object in a 200 body. This service
        **absorbs** it (spec per-service table): the whole batch's names are omitted from the result
        (a retry-later signal), never recorded as a confirmed "no such size" — exactly the
        omit-on-failure degrade the hand-rolled retry produced before.
        """
        by_norm = {self._norm(n): n for n in batch}
        params = {
            "action": "query",
            "format": "json",
            "prop": "categoryinfo",
            "titles": "|".join(f"Category:{n}" for n in batch),
        }
        try:
            data = await transport.get_json(WIKIPEDIA_API, params=params)
        except WikidataUnavailable:
            return (
                {}
            )  # unreachable batch → omit its names (retry later), never a false absence
        result: dict[str, int] = {}
        pages = (data.get("query") or {}).get("pages") or {}
        if not isinstance(pages, dict):
            return result
        for page in pages.values():
            title = str(page.get("title", ""))
            name = title[len("Category:") :] if title.startswith("Category:") else title
            original = by_norm.get(self._norm(name))
            info = page.get("categoryinfo")
            if original is not None and isinstance(info, dict):
                # `size` = total members (pages + subcategories + files).
                result[original] = int(info.get("size", 0))
        return result
