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
from datetime import UTC, datetime
from typing import Any

import httpx

from chronovista.models.wikidata_candidate import WikidataCandidate
from chronovista.services import wikidata_properties as wp

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
        self, name: str, entity_type: str, *, limit: int = 5, offset: int = 0
    ) -> list[WikidataCandidate]:
        """Return a relevance-ranked shortlist (at most ``limit``) for ``name``.

        ``offset`` pages deeper into the same ranked results (``wbsearchentities`` ``continue``),
        so a match for a common name that ranks below the first page is still reachable. Raises
        ``WikidataUnavailable`` on transport/rate-limit failure; returns ``[]`` when the knowledge
        base was reached but has no (further) match.
        """
        limit = max(1, limit)
        offset = max(0, offset)
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
                # `continue` is Wikidata's offset; it is also a Python keyword, so it
                # can only be passed via dict-unpacking. Omit at offset 0 (page 1).
                **({"continue": offset} if offset else {}),
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

    async def resolve_candidate(
        self, qid: str, entity_type: str
    ) -> WikidataCandidate | None:
        """Resolve one pasted Wikidata QID directly to a candidate.

        The create modal's "paste a QID" fallback: when a common name buries the wanted match
        below the paged results, the user supplies its QID (e.g. ``Q42``) and grounds to it in
        one step. Returns ``None`` for a malformed QID or one Wikidata does not know; raises
        ``WikidataUnavailable`` on transport/rate-limit failure (same contract as search).
        """
        q = qid.strip()
        if not (len(q) >= 2 and q[0] == "Q" and q[1:].isdigit() and int(q[1:]) >= 1):
            return None
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            details = await self._item_details(http, [q])
        finally:
            if owns:
                await http.aclose()
        det = details.get(q)
        if det is None:
            return None
        expected = EXPECTED_INSTANCE_OF.get(entity_type, set())
        instance_of = det.get("instance_of", [])
        return WikidataCandidate(
            qid=q,
            label=self._resolve_label({"id": q}, det.get("labels", {})),
            description=det.get("description"),
            instance_of=instance_of,
            statement_count=det.get("statements", 0),
            sitelink_count=det.get("sitelinks", 0),
            is_stub=bool(det.get("looks_like_author_stub", False)),
            type_matches=(bool(expected & set(instance_of)) if expected else False),
        )

    async def fetch_properties(self, qid: str) -> dict[str, Any]:
        """Fetch the curated property fields for one grounded entity (Feature 068).

        Two batched ``wbgetentities`` rounds — ``props=claims|descriptions|aliases`` to extract the
        curated ``WANTED`` / ``WANTED_LITERAL`` fields plus the item's own one-line description and
        aliases, then ``props=labels`` to resolve the item-reference value-QIDs to readable labels —
        assembled into the persisted verbatim shape ``{field: {"values", "qids", "source", "set_at"}}``
        (spec FR-002). An unresolved value-QID is kept as its QID (FR-007). The Wikidata description
        and aliases are captured as separate display-only reference blocks (``wikidata_description`` /
        ``wikidata_aliases``) that never touch the entity's curated ``description`` / ``entity_aliases``
        (FR-005/FR-006). Returns ``{}`` only when the item asserts no wanted property AND has no
        description/aliases.

        Parameters
        ----------
        qid : str
            The Wikidata QID of the just-grounded entity.

        Returns
        -------
        dict[str, Any]
            The property bag in the same shape the batch load persists.

        Raises
        ------
        WikidataUnavailable
            On transport error or rate-limit exhaustion — the caller degrades to "grounded, no
            properties; the next batch run fills them" (FR-006).
        """
        http = self._http or self._new_client()
        owns = self._http is None
        try:
            entity_data = await self._get(
                http,
                action="wbgetentities",
                ids=qid,
                props="claims|descriptions|aliases",
                languages=wp.LABEL_LANGS,
            )
            entity = (entity_data.get("entities") or {}).get(qid) or {}
            extracted = wp.extract_claims(entity.get("claims") or {})
            description = wp.pick_description(entity.get("descriptions") or {})
            aliases = wp.extract_aliases(entity.get("aliases") or {})
            if not extracted and not description and not aliases:
                return {}

            labels: dict[str, str] = {}
            pending = wp.value_qids(extracted)
            for i in range(0, len(pending), 50):
                chunk = pending[i : i + 50]
                label_data = await self._get(
                    http,
                    action="wbgetentities",
                    ids="|".join(chunk),
                    props="labels",
                    languages=wp.LABEL_LANGS,
                )
                for vqid, ent in (label_data.get("entities") or {}).items():
                    text = wp.pick_label(ent.get("labels") or {})
                    if text:
                        labels[vqid] = text
        finally:
            if owns:
                await http.aclose()

        set_at = datetime.now(UTC).isoformat()
        properties = wp.assemble_properties(extracted, labels, set_at)
        # Display-only reference blocks — kept separate from curated fields (FR-005/FR-006).
        if description:
            properties["wikidata_description"] = wp.assemble_reference_block(
                [description], set_at
            )
        if aliases:
            properties["wikidata_aliases"] = wp.assemble_reference_block(
                aliases, set_at
            )
        return properties

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
                props="claims|sitelinks|labels|descriptions",
                languages=_LABEL_LANGS,
            )
            for qid, ent in (data.get("entities") or {}).items():
                if "missing" in ent:
                    # A QID Wikidata does not know (e.g. a mistyped paste) — skip it
                    # so callers see it as unresolved rather than an empty candidate.
                    continue
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
                # Description in the same fallback order as labels — used when a
                # candidate is resolved directly by QID (no search hit to read it from).
                description: str | None = None
                descriptions = ent.get("descriptions") or {}
                for lang in ("en", "mul", "en-gb"):
                    entry = descriptions.get(lang)
                    if isinstance(entry, dict) and entry.get("value"):
                        description = str(entry["value"])
                        break
                out[qid] = {
                    "instance_of": vals,
                    "sitelinks": sitelinks,
                    "statements": statements,
                    "labels": ent.get("labels") or {},
                    "description": description,
                    "looks_like_author_stub": (
                        "P496" in claims
                        and statements <= _STUB_MAX_STATEMENTS
                        and sitelinks == 0
                    ),
                }
        return out
