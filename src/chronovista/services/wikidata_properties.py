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

# Wikidata property -> our field name. Item-valued: the value is a QID that must be resolved to a
# readable label. This is the single source; the batch pipeline imports it rather than keeping its
# own copy (#258) — P27 and P17 both fold into "country"; P31 is the entity-type cross-check.
WANTED: dict[str, str] = {
    "P31": "instance_of",
    "P279": "subclass_of",
    "P106": "occupation",
    "P27": "country",
    "P17": "country",
    "P39": "position_held",
    "P21": "sex_or_gender",
    "P19": "place_of_birth",
    "P69": "educated_at",
    "P108": "employer",
    "P102": "political_party",
    "P463": "member_of",
    "P1412": "languages",
    "P159": "headquarters",
    # Feature 079 — item-valued relations (values are QIDs resolved in the label round).
    "P26": "spouse",
    "P22": "father",
    "P25": "mother",
    "P40": "child",
    "P3373": "sibling",
    "P20": "place_of_death",
    "P101": "field_of_work",
    "P361": "part_of",
    "P451": "unmarried_partner",
    "P3342": "significant_person",
}

# Literal-valued: strings, URLs and dates that ARE the value (no label round needed).
WANTED_LITERAL: dict[str, str] = {
    "P569": "birth_date",
    "P570": "death_date",
    "P571": "inception",
    "P856": "official_website",
    "P2397": "youtube_channel_id",
    "P345": "imdb_id",
    "P2002": "x_username",
    "P2003": "instagram_username",
    # Feature 079 — portrait image (commonsMedia serializes as a "string" filename),
    # monolingual names, and the remaining social-identifier platforms (no follower counts).
    "P18": "image",
    "P1559": "native_language_name",
    "P1477": "birth_name",
    "P2013": "facebook_id",
    "P7085": "tiktok_username",
    "P4033": "mastodon_address",
}

# Value-label languages. Some items carry only Wikidata's cross-lingual ``mul`` label — invisible to
# a chain that asks for ``en`` alone. Order defines resolution preference.
LABEL_LANGS = "mul|en|en-gb|en-ca|es|fr|de|it|pt|nl"
LABEL_ORDER = ("mul", "en", "en-gb", "en-ca", "es", "fr", "de", "it", "pt", "nl")


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
