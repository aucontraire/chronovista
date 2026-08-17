"""
Wikidata client for create-time grounding (Feature 067, US3).

An async, bounded, degradation-safe client that returns a ranked candidate shortlist for the
entity-creation approval flow. It mirrors the parsing the untracked entity-resolution pipeline
uses (``wbsearchentities`` → ``wbgetentities`` with ``claims|sitelinks``), but async and with a
timeout so an interactive create is never left hanging on the knowledge base (FR-015).

No DBpedia call happens here — a newly grounded entity's DBpedia IRI is filled later by the
back-fill (spec Non-Goals). On any transport failure or rate-limit exhaustion the client raises
``WikidataUnavailable`` so the caller can degrade to "creation proceeds ungrounded" (FR-012),
which is distinct from an empty shortlist meaning "no match".
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from chronovista.models.wikidata_candidate import WikidataCandidate

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "chronovista/1.0 (local personal library tooling)"

# Instance_of (P31) values that corroborate a hand-assigned type. Mirrors the pipeline's
# deliberately-narrow map (sweep_absent_wikidata.EXPECTED): a wrong "matches" is costlier than
# a missed one, since it is the signal a reviewer most trusts.
EXPECTED_INSTANCE_OF: dict[str, set[str]] = {
    "person": {"Q5"},
    "place": {"Q6256", "Q3624078", "Q515", "Q15284", "Q7275", "Q82794", "Q23442"},
    "organization": {
        "Q4830453",
        "Q43229",
        "Q783794",
        "Q7278",
        "Q1616075",
        "Q11033",
        "Q163740",
        "Q3918",
        "Q1002697",
    },
}

# Thin + sitelink-less + ORCID-only is the signature of an item auto-generated from a
# publication author list (ADR-010 D5 / FR-013).
_STUB_MAX_STATEMENTS = 10
_LABEL_LANGS = "en|mul|en-gb"  # BCP-47 fallback order for FR-016
_DEFAULT_TIMEOUT = 8.0
_MAX_RATE_LIMIT_RETRIES = 2


class WikidataUnavailable(Exception):
    """The knowledge base could not be reached (timeout, transport error, or rate-limited).

    Distinct from an empty result: the caller degrades to ungrounded creation and surfaces a
    'couldn't reach the knowledge base' signal rather than a benign 'no match' (FR-012).
    """


class WikidataClient:
    """Async Wikidata search client for create-time grounding."""

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

    async def _get(self, http: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
        """One API call, retrying a rate limit within a bounded number of attempts."""
        params.setdefault("format", "json")
        for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
            try:
                resp = await http.get(API, params=params)
            except httpx.HTTPError as exc:
                raise WikidataUnavailable(str(exc)) from exc
            if resp.status_code == 429 and attempt < _MAX_RATE_LIMIT_RETRIES:
                try:
                    wait = min(int(resp.headers.get("Retry-After", "1")), 5)
                except ValueError:
                    wait = 1
                await asyncio.sleep(wait)
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise WikidataUnavailable(str(exc)) from exc
            data: dict[str, Any] = resp.json()
            return data
        raise WikidataUnavailable("rate limited repeatedly")

    async def search_candidates(
        self, name: str, entity_type: str, *, limit: int = 5
    ) -> list[WikidataCandidate]:
        """Return a relevance-ranked shortlist (at most ``limit``) for ``name``.

        Raises ``WikidataUnavailable`` on transport/rate-limit failure; returns ``[]`` when the
        knowledge base was reached but has no match.
        """
        limit = max(1, limit)
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            search = await self._get(
                http,
                action="wbsearchentities",
                search=name,
                language="en",
                uselang="en",
                type="item",
                limit=limit,
            )
            hits = [h for h in search.get("search", []) if h.get("id")][:limit]
            if not hits:
                return []
            qids = [str(h["id"]) for h in hits]
            details = await self._item_details(http, qids)
        finally:
            if owns:
                await http.aclose()

        expected = EXPECTED_INSTANCE_OF.get(entity_type, set())
        candidates: list[WikidataCandidate] = []
        for hit in hits:
            qid = str(hit["id"])
            det = details.get(qid, {})
            instance_of = det.get("instance_of", [])
            candidates.append(
                WikidataCandidate(
                    qid=qid,
                    label=self._resolve_label(hit, det.get("labels", {})),
                    description=hit.get("description"),
                    instance_of=instance_of,
                    statement_count=det.get("statements", 0),
                    sitelink_count=det.get("sitelinks", 0),
                    is_stub=bool(det.get("looks_like_author_stub", False)),
                    type_matches=(
                        bool(expected & set(instance_of)) if expected else False
                    ),
                )
            )
        return candidates

    @staticmethod
    def _resolve_label(hit: dict[str, Any], labels: dict[str, Any]) -> str:
        """FR-016: prefer the search label, else fall back through en → mul → en-gb."""
        label = hit.get("label")
        if isinstance(label, str) and label:
            return label
        for lang in ("en", "mul", "en-gb"):
            entry = labels.get(lang)
            if isinstance(entry, dict) and entry.get("value"):
                return str(entry["value"])
        # A missing label is reported as the QID, never as "no label".
        return str(hit.get("id", ""))

    async def _item_details(
        self, http: httpx.AsyncClient, qids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """P31 values, statement/sitelink/stub signals, and labels — one call per chunk.

        Fetches ``claims|sitelinks|labels`` together (labels in the fallback languages) so the
        create path makes one ``wbgetentities`` round-trip per 50 items instead of two.
        """
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(qids), 50):
            chunk = qids[i : i + 50]
            data = await self._get(
                http,
                action="wbgetentities",
                ids="|".join(chunk),
                props="claims|sitelinks|labels",
                languages=_LABEL_LANGS,
            )
            for qid, ent in (data.get("entities") or {}).items():
                claims = ent.get("claims") or {}
                vals: list[str] = []
                for claim in claims.get("P31", []):
                    dv = claim.get("mainsnak", {}).get("datavalue")
                    if dv and isinstance(dv.get("value"), dict):
                        cid = dv["value"].get("id")
                        if cid:
                            vals.append(str(cid))
                statements = sum(len(v) for v in claims.values())
                sitelinks = len(ent.get("sitelinks") or {})
                out[qid] = {
                    "instance_of": vals,
                    "sitelinks": sitelinks,
                    "statements": statements,
                    "labels": ent.get("labels") or {},
                    "looks_like_author_stub": (
                        "P496" in claims
                        and statements <= _STUB_MAX_STATEMENTS
                        and sitelinks == 0
                    ),
                }
        return out
