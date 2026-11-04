"""Seam parity guard (Feature 105, ADR 014): the committed relation-membership JSON the frontend
derives ``RELATION_KEYS`` from MUST equal a fresh generation from the backend ``RELATIONS``.

This crosses the backend→committed-artifact seam in one assertion — the contract whose drift is bug B
(an item-valued relation falling through to unlinked static text). It is the freshness gate: if
``RELATIONS`` changes and ``scripts/utilities/gen_relation_fields.py`` wasn't re-run + committed, this
fails in CI. Server-free (pure import + file read).
"""

from __future__ import annotations

import json
from pathlib import Path

from chronovista.services.wikidata_properties import RELATIONS

_JSON = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "generated"
    / "relation-fields.json"
)


def test_relation_fields_json_matches_relations() -> None:
    committed = json.loads(_JSON.read_text(encoding="utf-8"))["relations"]
    expected = sorted(set(RELATIONS.values()))
    assert committed == expected, (
        "frontend/src/generated/relation-fields.json is stale — run "
        "`poetry run python scripts/utilities/gen_relation_fields.py` and commit the result."
    )
