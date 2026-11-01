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

from datetime import UTC, datetime
from typing import Any

import httpx

from chronovista.models.wikidata_candidate import WikidataCandidate
from chronovista.services import wikidata_properties as wp
from chronovista.services.wikidata_taxonomy import (
    EXPECTED_INSTANCE_OF as EXPECTED_INSTANCE_OF,  # re-export: single source (Feature 098)
)
from chronovista.services.wikidata_taxonomy import (
    suggest_entity_type,
    type_corroboration,
)
from chronovista.services.wikimedia_transport import (
    WikidataUnavailable as WikidataUnavailable,  # re-export: canonical def lives in transport
)
from chronovista.services.wikimedia_transport import (
    WikimediaTransport,
    wikimedia_user_agent,
)

API = "https://www.wikidata.org/w/api.php"
# The per-client component label for the single-sourced outbound identity (G1/FR-002). Wikimedia's
# User-Agent policy gates request rate on a contact-bearing UA (~10 vs ~200 req/min, ADR-010); the
# transport assembles the compliant string (product/version/contact + this label) — no UA is
# hand-built here. ``USER_AGENT`` is derived from the template (not reassembled) and kept as a
# module export because out-of-scope callers (``wikipedia_image_fallback``, the gitignored B2
# scripts) still import it; Phase B1 does not touch those.
_UA_COMPONENT = "personal YouTube-library tool"
USER_AGENT = wikimedia_user_agent(_UA_COMPONENT)

# P31→type knowledge now lives in the shared classifier (Feature 098): EXPECTED_INSTANCE_OF is
# imported/re-exported above and the corroboration rule is delegated below, so the create badge and
# the candidate classifier cannot drift (single source of truth). The callers of
# ``_type_verification`` below are unchanged.


def _type_verification(entity_type: str | None, instance_of: list[str]) -> bool | None:
    """Tri-state type corroboration for a Wikidata candidate (#271).

    Thin wrapper over the shared ``wikidata_taxonomy.type_corroboration`` (Feature 098).
    Semantics unchanged: ``True`` (agrees) / ``False`` ("type may differ") / ``None`` (neutral —
    no reliable expected set; render as absent, never as "may differ").
    """
    return type_corroboration(entity_type, instance_of)


# Thin + sitelink-less + ORCID-only is the signature of an item auto-generated from a
# publication author list (ADR-010 D5 / FR-013).
_STUB_MAX_STATEMENTS = 10
_LABEL_LANGS = "en|mul|en-gb"  # BCP-47 fallback order for FR-016
_DEFAULT_TIMEOUT = 8.0


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

    def _transport(self) -> WikimediaTransport:
        """The shared outbound transport for this client (FR-001).

        Preserves the ``http=None`` injection seam (per-request client by default; the injected
        client reused when supplied). The transport owns UA assembly, the unified retry/backoff
        (incl. 429/Retry-After and transient transport errors), non-JSON-200 detection, and the
        MediaWiki ``{"error":...}``-in-200 detection generalized across the fetch layer (FR-005) —
        so an upstream error now raises ``WikidataUnavailable`` here instead of returning a
        misleading empty payload.
        """
        return WikimediaTransport(_UA_COMPONENT, http=self._http, timeout=self._timeout)

    async def _call(
        self, transport: WikimediaTransport, **params: Any
    ) -> dict[str, Any]:
        """One Wikidata action-API GET through the transport (adds the JSON ``format`` default).

        Raises ``WikidataUnavailable`` on transport failure, exhausted retries, a non-JSON 200
        body, or an error object in a 200 body (all now owned by the transport). A reached-but-empty
        result is returned as data, never raised.
        """
        params.setdefault("format", "json")
        return await transport.get_json(API, params=params)

    async def search_candidates(
        self,
        name: str,
        entity_type: str | None = None,
        *,
        limit: int = 5,
        offset: int = 0,
    ) -> list[WikidataCandidate]:
        """Return a relevance-ranked shortlist (at most ``limit``) for ``name``.

        ``offset`` pages deeper into the same ranked results (``wbsearchentities`` ``continue``),
        so a match for a common name that ranks below the first page is still reachable. Raises
        ``WikidataUnavailable`` on transport/rate-limit failure; returns ``[]`` when the knowledge
        base was reached but has no (further) match.
        """
        limit = max(1, limit)
        offset = max(0, offset)
        transport = self._transport()
        search = await self._call(
            transport,
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
        details = await self._item_details(transport, qids)

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
                    type_matches=_type_verification(entity_type, instance_of),
                    suggested_entity_type=suggest_entity_type(instance_of),
                )
            )
        return candidates

    async def fetch_instance_of(self, qids: list[str]) -> dict[str, list[str]]:
        """Batched P31 (``instance_of``) for many QIDs (Feature 098).

        Public wrapper over the one batched ``wbgetentities`` fetch (50/chunk), returning
        ``{qid: [p31 qids]}`` for the QIDs Wikidata knows (unknown QIDs are omitted). Reuses the
        single fetch path so candidate typing, the backfill, and approval re-verification share it.
        Raises ``WikidataUnavailable`` on transport/rate-limit failure so callers can degrade.
        """
        if not qids:
            return {}
        details = await self._item_details(self._transport(), qids)
        return {qid: list(det.get("instance_of") or []) for qid, det in details.items()}

    async def fetch_sitelinks(self, qids: list[str]) -> dict[str, dict[str, str]]:
        """Batched Wikipedia sitelinks for many QIDs (Feature 100).

        Returns ``{qid: {wiki_dbname: article_title}}`` restricted to **Wikipedia** projects
        (``*wiki`` keys, excluding Commons / Wikispecies / Meta / Wikidata and other sister
        projects, per FR-002). The caller derives a language subdomain from a dbname by dropping
        the ``wiki`` suffix (``eswiki`` → ``es``). Batched 50 ids/request (the ``wbgetentities``
        ceiling, FR-016) over the shared polite client; raises ``WikidataUnavailable`` on
        transport/rate-limit failure so callers can degrade (FR-014).
        """
        if not qids:
            return {}
        non_wikipedia = frozenset(
            {
                # sister projects + Wikimedia admin wikis whose dbname ends in "wiki" but which
                # are NOT language Wikipedias (sister projects like enwiktionary/enwikinews end in
                # "wiktionary"/"wikinews" and are already excluded by the endswith("wiki") filter).
                "commonswiki",
                "specieswiki",
                "metawiki",
                "wikidatawiki",
                "sourceswiki",
                "mediawikiwiki",
                "wikimaniawiki",
                "incubatorwiki",
                "testwiki",
                "test2wiki",
                "outreachwiki",
                "donatewiki",
                "foundationwiki",
                "nostalgiawiki",
            }
        )
        transport = self._transport()
        out: dict[str, dict[str, str]] = {}
        for chunk in WikimediaTransport.chunk(
            qids
        ):  # 50 ids/request (wbgetentities ceiling)
            data = await self._call(
                transport,
                action="wbgetentities",
                ids="|".join(chunk),
                props="sitelinks",
            )
            entities = data.get("entities") or {}
            for qid, ent in entities.items():
                if not isinstance(ent, dict) or "missing" in ent:
                    continue
                sitelinks = ent.get("sitelinks") or {}
                wikis: dict[str, str] = {}
                for dbname, link in sitelinks.items():
                    title = link.get("title") if isinstance(link, dict) else None
                    if (
                        isinstance(dbname, str)
                        and dbname.endswith("wiki")
                        and dbname not in non_wikipedia
                        and isinstance(title, str)
                        and title
                    ):
                        wikis[dbname] = title
                out[str(qid)] = wikis
        return out

    async def resolve_candidate(
        self, qid: str, entity_type: str | None = None
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
        details = await self._item_details(self._transport(), [q])
        det = details.get(q)
        if det is None:
            return None
        instance_of = det.get("instance_of", [])
        return WikidataCandidate(
            qid=q,
            label=self._resolve_label({"id": q}, det.get("labels", {})),
            description=det.get("description"),
            instance_of=instance_of,
            statement_count=det.get("statements", 0),
            sitelink_count=det.get("sitelinks", 0),
            is_stub=bool(det.get("looks_like_author_stub", False)),
            type_matches=_type_verification(entity_type, instance_of),
            suggested_entity_type=suggest_entity_type(instance_of),
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
            On transport error or rate-limit exhaustion (after the transport's bounded retries).
            The caller degrades to "grounded, no properties" — and, because the enrichment path is
            one-shot and detached with no scheduled sweeper, those properties are NOT filled by any
            later batch run; they remain absent until a manual reground. The transport's retry is
            the only retry this path gets (FR-006/FR-016).
        """
        transport = self._transport()
        entity_data = await self._call(
            transport,
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
        for chunk in WikimediaTransport.chunk(
            pending
        ):  # 50 ids/request (wbgetentities ceiling)
            label_data = await self._call(
                transport,
                action="wbgetentities",
                ids="|".join(chunk),
                props="labels",
                languages=wp.LABEL_LANGS,
            )
            for vqid, ent in (label_data.get("entities") or {}).items():
                text = wp.pick_label(ent.get("labels") or {})
                if text:
                    labels[vqid] = text

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
        self, transport: WikimediaTransport, qids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """P31 values, statement/sitelink/stub signals, and labels — one call per chunk.

        Fetches ``claims|sitelinks|labels`` together (labels in the fallback languages) so the
        create path makes one ``wbgetentities`` round-trip per 50 items instead of two.
        """
        out: dict[str, dict[str, Any]] = {}
        for chunk in WikimediaTransport.chunk(
            qids
        ):  # 50 ids/request (wbgetentities ceiling)
            data = await self._call(
                transport,
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
