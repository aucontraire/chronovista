"""
Wikipedia free-Commons image fallback — fetch + legal gate (Feature 093).

For a grounded entity with no image, this resolves the entity's English Wikipedia page from its
Wikidata QID, reads the page's **free** lead image, and confirms that file is hosted on Wikimedia
**Commons** and not flagged non-free before accepting it. The accepted value is a bare Commons
filename the existing resolver serves unchanged (FR-004); nothing else is ever stored.

The gate is the load-bearing legal invariant (FR-002): store an image ONLY when it is
Commons-hosted AND not non-free. The three external calls are, per candidate:

1. **Wikidata** ``wbgetentities props=sitelinks sitefilter=enwiki`` → the English Wikipedia title
   (mirrors :meth:`dbpedia_resolver.DbpediaResolver._enwiki_title`). No sitelink → ``NO_PAGE``.
2. **English Wikipedia** ``prop=pageprops`` → ``page_image_free`` (the PageImages extension's
   free-designated lead image, which excludes non-free candidates). Absent → ``NO_LEAD_IMAGE``.
3. **English Wikipedia** ``prop=imageinfo iiprop=extmetadata`` on ``File:<name>`` → the page's
   ``imagerepository`` (``"shared"`` = Commons, ``"local"`` = a local fair-use upload) and the
   ``NonFree`` flag. ``local`` → ``DECLINED_NOT_COMMONS``; a non-free or unverifiable file →
   ``DECLINED_NON_FREE``; Commons-hosted + not-non-free → ``STORED``.

Degradation-safe (Constitution VIII / FR-008): every transport error, timeout, or exhausted
rate-limit retry resolves to a :class:`FallbackOutcome.ERROR` result — the method never raises
past the per-entity boundary, so one entity's failure never aborts the backfill.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx

from chronovista.models.wikipedia_image import FallbackOutcome, FallbackResult
from chronovista.services.wikidata_client import USER_AGENT

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"

_DEFAULT_TIMEOUT = 8.0
_MAX_RATE_LIMIT_RETRIES = 2
_MAX_RETRY_AFTER = 5


class _FetchError(Exception):
    """An external call failed (transport, HTTP status, or exhausted rate-limit retries).

    Internal only: :meth:`WikipediaImageFallback.evaluate` catches it at the per-entity boundary
    and records :class:`FallbackOutcome.ERROR`, so it never propagates to the backfill loop.
    """


def _is_non_free(extmetadata: dict[str, Any]) -> bool:
    """True when the Commons ``extmetadata`` block flags the file non-free (``NonFree == "1"``).

    A free file either omits ``NonFree`` or carries ``"0"`` — absence means *not flagged*, which on
    a Commons-hosted file is the expected free case (Commons' free-only policy is the primary
    guarantee; this flag is the confirming check — clarification Q1).
    """
    entry = extmetadata.get("NonFree")
    raw = entry.get("value") if isinstance(entry, dict) else entry
    if raw is None:
        return False
    # extmetadata values are normally the string "1"/"0", but harden against a "true"/"yes"/bool
    # encoding so a flagged file can never slip through to STORED on a formatting difference.
    return str(raw).strip().lower() in ("1", "true", "yes")


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a dict, else ``{}``.

    MediaWiki's legacy JSON format (the default, without ``formatversion=2``) serialises an empty
    associative array as ``[]`` rather than ``{}`` — so ``entity.get("sitelinks", {})`` can hand
    back a *list* when the key is present-but-empty, and a later ``.get()`` would raise
    ``AttributeError`` and escape the per-entity boundary. Coercing every nested lookup through this
    helper turns an empty/odd collection into "absent" (→ a proven absence outcome), never a crash.
    """
    return value if isinstance(value, dict) else {}


class WikipediaImageFallback:
    """Resolve and legally gate an entity's English Wikipedia free-Commons lead image."""

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

    async def _get(
        self, http: httpx.AsyncClient, api: str, **params: Any
    ) -> dict[str, Any]:
        """One Wikimedia API call, retrying a 429 within a bounded budget.

        Mirrors :meth:`WikidataClient._get`: honours ``Retry-After`` (capped), and raises
        :class:`_FetchError` on transport failure, a non-2xx status, or an exhausted retry budget —
        so the caller converts any failure into a single ``ERROR`` outcome (FR-008).
        """
        params.setdefault("format", "json")
        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
            try:
                resp = await http.get(api, params=params)
            except httpx.HTTPError as exc:
                raise _FetchError(str(exc)) from exc
            if resp.status_code == 429 and attempt < _MAX_RATE_LIMIT_RETRIES:
                try:
                    wait = min(
                        int(resp.headers.get("Retry-After", "1")), _MAX_RETRY_AFTER
                    )
                except ValueError:
                    wait = 1
                await asyncio.sleep(wait)
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise _FetchError(str(exc)) from exc
            try:
                data: dict[str, Any] = resp.json()
            except ValueError as exc:
                # A 200 carrying a non-JSON body (a proxy/CAPTCHA/interstitial HTML page, a
                # truncated body) is a FAILURE, not an absence — raise so the per-entity boundary
                # records ERROR rather than a crash or a false "no image" (FR-008).
                raise _FetchError(f"non-JSON response from {api}: {exc}") from exc
            # MediaWiki reports many failures (ratelimited, maxlag, bad params) as HTTP 200 with an
            # ``{"error": {...}}`` body. Treat it as a failure (ERROR), never a proven absence —
            # otherwise a transient server error is settled permanently as "no page / no image"
            # and the entity is never retried (FR-007).
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                code = err.get("code") if isinstance(err, dict) else None
                raise _FetchError(f"api error from {api}: {code or 'unknown'}")
            return data
        raise _FetchError("rate limited repeatedly")

    async def evaluate(self, entity_id: UUID, qid: str) -> FallbackResult:
        """Evaluate one entity's English Wikipedia lead image and return its single outcome.

        Never raises: a resolved failure is a :class:`FallbackOutcome.ERROR` result (FR-008).

        Parameters
        ----------
        entity_id : UUID
            The entity being evaluated (echoed into the result for the run summary).
        qid : str
            The entity's Wikidata QID (``external_ids.wikidata.id``).

        Returns
        -------
        FallbackResult
            Exactly one outcome; ``filename`` is set only when ``STORED``.
        """
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            return await self._evaluate(http, entity_id, qid)
        except _FetchError as exc:
            return FallbackResult(
                entity_id=entity_id, outcome=FallbackOutcome.ERROR, detail=str(exc)
            )
        finally:
            if owns:
                await http.aclose()

    async def _evaluate(
        self, http: httpx.AsyncClient, entity_id: UUID, qid: str
    ) -> FallbackResult:
        title = await self._enwiki_title(http, qid)
        if not title:
            return FallbackResult(
                entity_id=entity_id,
                outcome=FallbackOutcome.NO_PAGE,
                detail=f"no enwiki sitelink for {qid}",
            )

        filename = await self._free_lead_image(http, title)
        if not filename:
            return FallbackResult(
                entity_id=entity_id, outcome=FallbackOutcome.NO_LEAD_IMAGE
            )

        outcome = await self._confirm_free_commons(http, filename)
        if outcome is FallbackOutcome.STORED:
            return FallbackResult(
                entity_id=entity_id,
                outcome=FallbackOutcome.STORED,
                filename=filename,
            )
        return FallbackResult(entity_id=entity_id, outcome=outcome)

    async def _enwiki_title(self, http: httpx.AsyncClient, qid: str) -> str | None:
        """The item's English Wikipedia article title from its Wikidata sitelink, if any."""
        data = await self._get(
            http,
            WIKIDATA_API,
            action="wbgetentities",
            ids=qid,
            props="sitelinks",
            sitefilter="enwiki",
        )
        entity = _as_dict(_as_dict(data.get("entities")).get(qid))
        enwiki = _as_dict(_as_dict(entity.get("sitelinks")).get("enwiki"))
        title = enwiki.get("title")
        return str(title) if title else None

    async def _free_lead_image(self, http: httpx.AsyncClient, title: str) -> str | None:
        """The page's free-designated lead image filename (``page_image_free``), if any."""
        data = await self._get(
            http,
            ENWIKI_API,
            action="query",
            prop="pageprops",
            ppprop="page_image_free",
            titles=title,
            redirects=1,
        )
        pages = _as_dict(_as_dict(data.get("query")).get("pages"))
        page = next(iter(pages.values()), None)
        if not isinstance(page, dict):
            return None
        filename = _as_dict(page.get("pageprops")).get("page_image_free")
        return str(filename) if filename else None

    async def _confirm_free_commons(
        self, http: httpx.AsyncClient, filename: str
    ) -> FallbackOutcome:
        """Confirm the file is Commons-hosted AND not non-free — the FR-002 legal gate.

        Queries the file's ``imageinfo`` on English Wikipedia (where ``imagerepository`` reports
        ``"shared"`` for a Commons file vs ``"local"`` for a fair-use upload). A local upload is
        ``DECLINED_NOT_COMMONS``; a non-free or unverifiable file is ``DECLINED_NON_FREE``
        (conservative); only a Commons-hosted, not-non-free file is accepted (``STORED``).
        """
        data = await self._get(
            http,
            ENWIKI_API,
            action="query",
            prop="imageinfo",
            iiprop="extmetadata",
            titles=f"File:{filename}",
        )
        pages = _as_dict(_as_dict(data.get("query")).get("pages"))
        page = next(iter(pages.values()), None)
        if not isinstance(page, dict):
            return FallbackOutcome.DECLINED_NON_FREE

        repository = page.get("imagerepository")
        if repository == "local":
            return FallbackOutcome.DECLINED_NOT_COMMONS
        if repository != "shared":
            # Unknown / empty repository (e.g. the file page is missing): cannot confirm Commons
            # hosting, so decline conservatively rather than store an unverifiable file (FR-002).
            return FallbackOutcome.DECLINED_NON_FREE

        imageinfo = page.get("imageinfo")
        if not (isinstance(imageinfo, list) and imageinfo):
            return FallbackOutcome.DECLINED_NON_FREE
        extmetadata = _as_dict(imageinfo[0]).get("extmetadata")
        if _is_non_free(_as_dict(extmetadata)):
            return FallbackOutcome.DECLINED_NON_FREE
        return FallbackOutcome.STORED
