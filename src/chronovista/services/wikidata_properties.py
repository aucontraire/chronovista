"""
Curated Wikidata property extraction (Feature 068).

The single **tracked** definition of the curated property field set and the pure claim/label
extraction logic. Ported from the gitignored entity-resolution pipeline
(``scripts/entity_resolution/fetch_properties.py``) so shipped code no longer depends on an
untracked file that is absent in the deployed container.

The output shape is the load-bearing contract (spec FR-002): each field is assembled into the
**verbatim** per-field block the batch load persists and mirrors —
``{"values": [...], "qids": [...], "source": "wikidata", "set_at": "<iso>"}`` — verified against the
production ``named_entities.properties`` shape. A newly grounded entity written from this module and
one written by a later batch load agree by construction (only the per-run ``set_at`` differs).

Everything here is pure (no I/O): ``WikidataClient.fetch_properties`` performs the two API rounds and
calls these functions, and the unit test pins the shape as the parity anchor.

SINGLE SOURCE OF TRUTH (#258): the gitignored batch pipeline
(``scripts/entity_resolution/fetch_properties.py``) imports ``WANTED`` / ``WANTED_LITERAL`` / the
extractors from here and no longer redefines them, so the batch writer and the on-approval writer
cannot drift. Anything added here (a new property, a new extractor) reaches both paths; nothing in
that script should re-declare these.
"""

from __future__ import annotations

import re
from typing import Any

SOURCE = "wikidata"

# ---------------------------------------------------------------------------------------------------
# Capture registry, grouped by KIND (the #258 single source).
#
# `kind` is the SEMANTIC axis — is a field a traversable graph edge, a node attribute, or an external
# identifier? It is ORTHOGONAL to the item/literal axis (does the value need a QID->label round?),
# which is what ``WANTED`` vs ``WANTED_LITERAL`` encode. Both public dicts are DERIVED from these four
# groups, byte-for-byte identical to their historical contents, so every consumer
# (``extract_claims``, ``relation_groups``, the gitignored batch pipeline) is untouched.
#
# The knowledge-graph export derives its edge set from :data:`RELATIONS` instead of a hand-copied list
# that drifted: ``founder``/``cast_member``/``director``/``producer``/``screenwriter``/``composer``/
# ``significant_person``/``unmarried_partner``/``field_of_work`` were all captured in ``WANTED`` yet
# were never added to the export's parallel RELS list. Grouping them under ``RELATIONS`` closes that
# drift at the source. P27/P17 country, P31 instance_of, P21 sex_or_gender, P106 occupation, P1412
# languages and P159 headquarters are item-valued too, but are NODE ATTRIBUTES — the export emits them
# as scalar node fields, not edges, which ``ATTRIBUTES_ITEM`` records.
# ---------------------------------------------------------------------------------------------------

# RELATIONS — item-valued QID targets exported as traversable graph edges (entity -> entity).
# THIS is the single source for the graph export's relation set; adding a field here reaches both the
# enrichment writers (via the derived ``WANTED``) and the export (which reads ``RELATIONS``).
RELATIONS: dict[str, str] = {
    "P108": "employer",
    "P69": "educated_at",
    "P463": "member_of",
    "P19": "place_of_birth",
    "P20": "place_of_death",
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
    "P3373": "sibling",
    "P39": "position_held",
    "P102": "political_party",
    "P361": "part_of",
    "P279": "subclass_of",
    # Feature 087 — organization founders.
    "P112": "founder",
    # Feature 088 — creative-work credit family (stored on the work, pointing at people).
    "P161": "cast_member",
    "P57": "director",
    "P162": "producer",
    "P58": "screenwriter",
    "P86": "composer",
    # Feature 079 — remaining item-valued relations.
    "P3342": "significant_person",
    "P451": "unmarried_partner",
    "P101": "field_of_work",
}

# ATTRIBUTES_ITEM — item-valued, but node attributes rather than edges (resolved to label strings).
# P27 and P17 both fold into "country"; P31 is the entity-type cross-check.
ATTRIBUTES_ITEM: dict[str, str] = {
    "P31": "instance_of",
    "P106": "occupation",
    "P27": "country",
    "P17": "country",
    "P21": "sex_or_gender",
    "P1412": "languages",
    "P159": "headquarters",
}

# ATTRIBUTES_LITERAL — literal node attributes (the value IS the datum; no label round).
ATTRIBUTES_LITERAL: dict[str, str] = {
    "P569": "birth_date",
    "P570": "death_date",
    "P571": "inception",
    # Feature 079 — portrait image (commonsMedia serializes as a "string" filename) + monolingual names.
    "P18": "image",
    "P1559": "native_language_name",
    "P1477": "birth_name",
}

# IDENTIFIERS — external-DB / social-platform IDs and URLs (literal node properties, never edges).
IDENTIFIERS: dict[str, str] = {
    "P856": "official_website",
    "P2397": "youtube_channel_id",
    "P345": "imdb_id",
    "P2002": "x_username",
    "P2003": "instagram_username",
    "P2013": "facebook_id",
    "P7085": "tiktok_username",
    "P4033": "mastodon_address",
}

# ---- Derived public contract — DO NOT hand-edit; add to the kind groups above. ----
# Item-valued: the value is a QID resolved to a readable label in the label round.
WANTED: dict[str, str] = {**RELATIONS, **ATTRIBUTES_ITEM}
# Literal-valued: strings, URLs and dates that ARE the value (no label round needed).
WANTED_LITERAL: dict[str, str] = {**ATTRIBUTES_LITERAL, **IDENTIFIERS}

# Value-label languages. Some items carry only Wikidata's cross-lingual ``mul`` label — invisible to
# a chain that asks for ``en`` alone. Order defines resolution preference.
LABEL_LANGS = "mul|en|en-gb|en-ca|es|fr|de|it|pt|nl"
LABEL_ORDER = ("mul", "en", "en-gb", "en-ca", "es", "fr", "de", "it", "pt", "nl")


def wikidata_qid(external_ids: Any) -> str | None:
    """Extract an entity's Wikidata QID from its ``external_ids`` bag, or ``None``.

    Tolerates BOTH shapes the column has carried: the legacy bare string
    (``{"wikidata": "Q42"}``, pre-Feature 067) and the structured dict
    (``{"wikidata": {"id": "Q42", ...}}``). The single source of this parse — three one-off copies
    (the referenced-by endpoint, both relation/category backfills) previously diverged, the oldest
    silently missing the bare-string case.
    """
    if not isinstance(external_ids, dict):
        return None
    value = external_ids.get("wikidata")
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        raw = value.get("id")
        return raw if isinstance(raw, str) and raw else None
    return None


def format_time(value: dict[str, Any]) -> str | None:
    """Render a Wikidata time value at the precision it actually claims.

    Wikidata pads every date to a full timestamp regardless of how much is known, so
    ``+1959-01-01T00:00:00Z`` at precision 9 means "1959", not "1 January". Emitting the padded form
    would invent a birthday.

    Parameters
    ----------
    value : dict[str, Any]
        The ``datavalue.value`` object of a ``time`` snak.

    Returns
    -------
    str | None
        The date at claimed precision (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, optionally
        ``... BCE``), or ``None`` for a decade-or-coarser precision that cannot be rendered as a
        specific date.
    """
    stamp = value.get("time", "")
    match = re.match(r"^([+-])(\d{4,})-(\d{2})-(\d{2})", stamp)
    if not match:
        return None
    sign, year, month, day = match.groups()
    precision = value.get("precision", 11)
    if precision >= 11:
        text = f"{year}-{month}-{day}"
    elif precision == 10:
        text = f"{year}-{month}"
    elif precision == 9:
        text = year
    else:
        return None
    return f"{text} BCE" if sign == "-" else text


def snak_value(snak: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(qid, literal)`` for one snak; at most one is set.

    Item references come back as a QID (to be resolved in the label round); time/monolingual/string
    values come back as a final literal. Any other datatype yields ``(None, None)`` and is dropped.
    """
    value = snak.get("datavalue", {}).get("value")
    datatype = snak.get("datavalue", {}).get("type")
    if datatype == "wikibase-entityid" and isinstance(value, dict):
        return value.get("id"), None
    if datatype == "time" and isinstance(value, dict):
        return None, format_time(value)
    if datatype == "monolingualtext" and isinstance(value, dict):
        return None, value.get("text")
    if datatype == "string" and isinstance(value, str):
        return None, value
    return None, None


def extract_claims(claims: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Pull the wanted properties out of one entity's ``claims`` block.

    Returns ``field -> {"qids": [...], "literals": [...]}``. Item references stay as QIDs so the
    caller can resolve them in one batched label round; literals are already final. Deprecated
    statements are skipped, and ``novalue`` / ``somevalue`` snaks are dropped — Wikidata uses those
    to assert *"unknown"*, which is not a value and must not be stored as one. Fields with neither a
    QID nor a literal are omitted.

    Parameters
    ----------
    claims : dict[str, Any]
        The ``claims`` object from a ``wbgetentities`` entity (``{"P31": [statement, ...], ...}``).

    Returns
    -------
    dict[str, dict[str, list[str]]]
        Per-field ``{"qids", "literals"}`` accumulator.
    """
    out: dict[str, dict[str, list[str]]] = {}
    for prop, field in {**WANTED, **WANTED_LITERAL}.items():
        for statement in claims.get(prop, []):
            if statement.get("rank") == "deprecated":
                continue
            snak = statement.get("mainsnak", {})
            if snak.get("snaktype") != "value":
                continue
            qid, literal = snak_value(snak)
            block = out.setdefault(field, {"qids": [], "literals": []})
            if qid and qid not in block["qids"]:
                block["qids"].append(qid)
            elif literal and literal not in block["literals"]:
                block["literals"].append(literal)
    return {f: b for f, b in out.items() if b["qids"] or b["literals"]}


def pick_label(labels: dict[str, Any]) -> str | None:
    """Resolve a value-item's label from its ``labels`` block using ``LABEL_ORDER``.

    Selects the **first language present** in ``LABEL_ORDER`` and returns its value verbatim — even
    if that value is an empty string. This mirrors the pipeline exactly
    (``next((lab[k]["value"] for k in LABEL_ORDER if k in lab), None)``): the caller stores the label
    only when it is truthy, so a present-but-empty label resolves to "no label" and the value-QID is
    kept unresolved — identical to a later batch load (FR-002). Selecting a *later* non-empty
    language instead would make the on-approval write diverge from the load.
    """
    for lang in LABEL_ORDER:
        entry = labels.get(lang)
        if isinstance(entry, dict) and "value" in entry:
            return str(entry["value"])
    return None


def assemble_block(
    qids: list[str], literals: list[str], labels: dict[str, str], set_at: str
) -> dict[str, Any]:
    """Assemble one field's persisted block in the verbatim shape (spec FR-002).

    Item references resolve to labels (unresolved ones stay as their QID — FR-007), then literals are
    appended; the raw ``qids`` and the ``source``/``set_at`` provenance are kept alongside.

    Parameters
    ----------
    qids : list[str]
        The item-reference QIDs for this field (pre-resolution).
    literals : list[str]
        The already-final literal values for this field.
    labels : dict[str, str]
        A ``{value_qid: label}`` map for the label round; a missing key leaves the QID as-is.
    set_at : str
        ISO timestamp stamped once per fetch (its value legitimately differs from a later load's).

    Returns
    -------
    dict[str, Any]
        ``{"values": [...], "qids": [...], "source": "wikidata", "set_at": set_at}``.
    """
    return {
        "values": [labels.get(q, q) for q in qids] + literals,
        "qids": qids,
        "source": SOURCE,
        "set_at": set_at,
    }


WIKIPEDIA_SOURCE = "wikipedia"


def wikipedia_image_block(filename: str, set_at: str) -> dict[str, Any]:
    """Assemble the automated-image block for a free Commons image sourced via Wikipedia (FR-003).

    Deliberately NOT :func:`assemble_block`: that helper hard-codes ``source == "wikidata"``, which
    the refetch merge (:func:`merge_wikidata_blocks`) treats as replaceable. A Wikipedia-sourced
    image must instead be tagged ``source == "wikipedia"`` so the merge *preserves* it across a
    property refetch that finds no P18, while a later real P18 (a fresh ``source == "wikidata"``
    block on the same ``"image"`` key) still overrides it (FR-005). The shape is otherwise identical
    to a Wikidata image block, so the resolver serves ``values[0]`` as a bare Commons filename with
    no change (FR-004).

    Parameters
    ----------
    filename : str
        A bare Wikimedia **Commons** ``File:`` name (no ``File:`` prefix, no URL) — the only form
        the Commons-only serving path resolves.
    set_at : str
        ISO timestamp of the backfill (also the resolver's ``?v=`` cache-buster).

    Returns
    -------
    dict[str, Any]
        ``{"values": [filename], "qids": [], "source": "wikipedia", "set_at": set_at}``.
    """
    return {
        "values": [filename],
        "qids": [],
        "source": WIKIPEDIA_SOURCE,
        "set_at": set_at,
    }


def value_qids(extracted: dict[str, dict[str, list[str]]]) -> list[str]:
    """Distinct value-QIDs across all fields, for a single batched label round (order-stable)."""
    seen: dict[str, None] = {}
    for block in extracted.values():
        for q in block["qids"]:
            seen.setdefault(q, None)
    return list(seen)


def assemble_properties(
    extracted: dict[str, dict[str, list[str]]], labels: dict[str, str], set_at: str
) -> dict[str, Any]:
    """Assemble the full property bag from extracted claims + a resolved-label map."""
    return {
        field: assemble_block(block["qids"], block["literals"], labels, set_at)
        for field, block in extracted.items()
    }


def pick_description(descriptions: dict[str, Any]) -> str | None:
    """Resolve the item's one-line description from its ``descriptions`` block using ``LABEL_ORDER``.

    Mirrors :func:`pick_label`: the first language present in ``LABEL_ORDER`` wins, returned verbatim.
    Sourced from the item's top-level ``descriptions`` (not from claims). Display-only reference data
    (spec FR-005/FR-006) — never merged into the entity's curated ``description`` column.
    """
    for lang in LABEL_ORDER:
        entry = descriptions.get(lang)
        if isinstance(entry, dict) and entry.get("value"):
            return str(entry["value"])
    return None


def extract_aliases(aliases: dict[str, Any]) -> list[str]:
    """Resolve the item's aliases from its ``aliases`` block using ``LABEL_ORDER``.

    Wikidata's ``aliases`` maps each language to a list of ``{"language", "value"}`` entries. Returns
    the values for the first language present in ``LABEL_ORDER`` (deduped, order-stable), or ``[]``.
    Display-only reference data (spec FR-005/FR-006) — never inserted into the ``entity_aliases`` table.
    """
    for lang in LABEL_ORDER:
        entries = aliases.get(lang)
        if isinstance(entries, list):
            out: list[str] = []
            for entry in entries:
                if isinstance(entry, dict):
                    value = entry.get("value")
                    if isinstance(value, str) and value and value not in out:
                        out.append(value)
            if out:
                return out
    return []


def assemble_reference_block(values: list[str], set_at: str) -> dict[str, Any]:
    """Assemble a display-only reference block (Wikidata description / aliases).

    Same provenance fields as :func:`assemble_block` but with no ``qids`` — these are not item
    references, just verbatim reference text kept separate from the entity's curated fields (FR-006).
    """
    return {"values": values, "source": SOURCE, "set_at": set_at}


def merge_wikidata_blocks(
    current: dict[str, Any], fresh: dict[str, Any]
) -> dict[str, Any]:
    """Merge a freshly-fetched Wikidata bag into an entity's existing ``properties`` (FR-015).

    Used by the backfill/refresh path. **Fully replaces the Wikidata-sourced blocks** — a key the
    source no longer asserts is dropped — while **preserving every block from another source** (e.g.
    DBpedia ``category`` blocks with ``source="dbpedia"``, or any hand-set block). A naive full-replace
    with ``fresh`` alone would silently wipe those (see ``replace_properties`` — full-replace is only
    safe on an already-merged bag), so refresh MUST go through this merge.

    Parameters
    ----------
    current : dict[str, Any]
        The entity's existing property bag (may hold blocks from multiple sources).
    fresh : dict[str, Any]
        A freshly-fetched bag whose blocks are all ``source == "wikidata"`` (from ``fetch_properties``).

    Returns
    -------
    dict[str, Any]
        ``{non-wikidata blocks of current} + {fresh}``.
    """
    preserved = {
        key: block
        for key, block in current.items()
        if not (isinstance(block, dict) and block.get("source") == SOURCE)
    }
    return {**preserved, **fresh}
