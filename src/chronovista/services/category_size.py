"""Fetch Wikipedia category global sizes (Feature 083, roadmap item ①).

A category's *specificity* is measured by its Wikipedia-wide member count — a stable property of
the category, unlike local library membership which drifts as the library grows. This service
reads that count from the live English Wikipedia API (``prop=categoryinfo``), batched, with a
Wikimedia-compliant contact User-Agent.

It is **name-free**: category names are runtime arguments, never embedded in source. (A gitignored
reference implementation lives under ``scripts/entity_resolution/``; that tree carries real entity
names and cannot be imported by tracked code, so this is the tracked, importable version — see the
feature's research notes.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any

import httpx

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "chronovista/1.0 (https://github.com/aucontraire/chronovista; category-size fetch)"
)
_DEFAULT_TIMEOUT = 15.0
_BATCH = 50  # MediaWiki titles-per-request limit for most query modules
_MAX_RETRIES = 3
_DEFAULT_PAUSE = 1.0  # polite gap (seconds) between batches — Wikimedia rate etiquette


class CategorySizeService:
    """Fetches Wikipedia-wide member counts for categories (best-effort)."""

    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        pause: float = _DEFAULT_PAUSE,
    ) -> None:
        self._timeout = timeout
        self._client_factory = client_factory or self._new_client
        self._pause = pause

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=self._timeout
        )

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
    ) -> dict[str, int]:
        by_norm = {self._norm(n): n for n in batch}
        params = {
            "action": "query",
            "format": "json",
            "prop": "categoryinfo",
            "titles": "|".join(f"Category:{n}" for n in batch),
        }
        data = await self._get(client, params)
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

    async def _get(
        self, client: httpx.AsyncClient, params: dict[str, str]
    ) -> dict[str, Any]:
        """One API call, retrying a transient failure a bounded number of times.

        Returns an empty dict if all attempts fail — the batch then yields no sizes, which the
        caller records as "unknown" rather than an error.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.get(WIKIPEDIA_API, params=params)
                resp.raise_for_status()
                parsed = resp.json()
                return dict(parsed) if isinstance(parsed, dict) else {}
            except httpx.HTTPError:
                if attempt == _MAX_RETRIES - 1:
                    return {}
                await asyncio.sleep(min(2**attempt, 5))
        return {}
