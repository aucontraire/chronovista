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

Degradation-safe (Constitution VIII / FR-008): every transport error, timeout, exhausted
rate-limit retry, non-JSON 200 body, or API-error object in a 200 body resolves to a
:class:`FallbackOutcome.ERROR` result — the method never raises past the per-entity boundary, so
one entity's failure never aborts the backfill. All three external calls now go through the shared
:class:`WikimediaTransport` (Feature 102): the transport owns the Wikimedia-compliant User-Agent,
the per-request client lifecycle, the unified rate-limit/backoff, and the error-200/non-JSON-200
detection (previously hand-rolled here). This service **absorbs** the transport's unreachable
signal (``WikidataUnavailable``) into its existing ``ERROR`` outcome per the spec's per-service
table — distinct from the proven absences ``NO_PAGE`` / ``NO_LEAD_IMAGE``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from chronovista.models.wikipedia_image import FallbackOutcome, FallbackResult
from chronovista.services.wikimedia_transport import (
    WikidataUnavailable,
    WikimediaTransport,
)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"

# The per-client component label baked into the single-sourced outbound User-Agent (G1/FR-002):
# the transport assembles the compliant UA from this label; no UA string is hand-built here, and it
# is no longer borrowed from ``wikidata_client``. The label is now this service's OWN descriptive
# name rather than the Wikidata client's generic one it used to reuse, so each of the five in-scope
# services carries a distinct component label (SC-002): the shared contact and template stay single-
# sourced while the identities remain distinguishable per request.
_UA_COMPONENT = "page-image fallback"

_DEFAULT_TIMEOUT = 8.0


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

    def _transport(self) -> WikimediaTransport:
        """The shared outbound transport for this service (FR-001).

        Preserves the ``http=None`` injection seam: a per-request client by default, or the injected
        client reused when one is supplied (tests/DI). UA assembly, the unified retry/backoff, the
        non-JSON-200 detection, and the MediaWiki ``{"error":...}``-in-200 detection all live in the
        transport now (the hand-rolled ``_get`` is gone).
        """
        return WikimediaTransport(_UA_COMPONENT, http=self._http, timeout=self._timeout)

    @staticmethod
    async def _get(
        transport: WikimediaTransport, api: str, **params: Any
    ) -> dict[str, Any]:
        """One Wikimedia API call through the shared transport (adds the JSON ``format`` default).

        Raises :class:`WikidataUnavailable` on transport failure, exhausted retries, a non-JSON 200
        body, or an API-error object in a 200 body (all now owned by the transport). The per-entity
        boundary in :meth:`evaluate` converts any such failure into a single ``ERROR`` outcome.
        """
        params.setdefault("format", "json")
        return await transport.get_json(api, params=params)

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
        transport = self._transport()
        try:
            return await self._evaluate(transport, entity_id, qid)
        except WikidataUnavailable as exc:
            return FallbackResult(
                entity_id=entity_id, outcome=FallbackOutcome.ERROR, detail=str(exc)
            )

    async def _evaluate(
        self, transport: WikimediaTransport, entity_id: UUID, qid: str
    ) -> FallbackResult:
        title = await self._enwiki_title(transport, qid)
        if not title:
            return FallbackResult(
                entity_id=entity_id,
                outcome=FallbackOutcome.NO_PAGE,
                detail=f"no enwiki sitelink for {qid}",
            )

        filename = await self._free_lead_image(transport, title)
        if not filename:
            return FallbackResult(
                entity_id=entity_id, outcome=FallbackOutcome.NO_LEAD_IMAGE
            )

        outcome = await self._confirm_free_commons(transport, filename)
        if outcome is FallbackOutcome.STORED:
            return FallbackResult(
                entity_id=entity_id,
                outcome=FallbackOutcome.STORED,
                filename=filename,
            )
        return FallbackResult(entity_id=entity_id, outcome=outcome)

    async def _enwiki_title(
        self, transport: WikimediaTransport, qid: str
    ) -> str | None:
        """The item's English Wikipedia article title from its Wikidata sitelink, if any."""
        data = await self._get(
            transport,
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

    async def _free_lead_image(
        self, transport: WikimediaTransport, title: str
    ) -> str | None:
        """The page's free-designated lead image filename (``page_image_free``), if any."""
        data = await self._get(
            transport,
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
        self, transport: WikimediaTransport, filename: str
    ) -> FallbackOutcome:
        """Confirm the file is Commons-hosted AND not non-free — the FR-002 legal gate.

        Queries the file's ``imageinfo`` on English Wikipedia (where ``imagerepository`` reports
        ``"shared"`` for a Commons file vs ``"local"`` for a fair-use upload). A local upload is
        ``DECLINED_NOT_COMMONS``; a non-free or unverifiable file is ``DECLINED_NON_FREE``
        (conservative); only a Commons-hosted, not-non-free file is accepted (``STORED``).
        """
        data = await self._get(
            transport,
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
