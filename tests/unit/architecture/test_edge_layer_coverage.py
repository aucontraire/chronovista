"""Contract guard: every graph edge class maps to a known EdgeLayer (Feature 115).

The edge-type → trust-layer taxonomy is a committed contract (``EdgeLayer`` docstring +
``edge_layer_for``). This guard mutation-verifies it: break the classifier and these fail.
It also enforces "no silent unknown" — an unclassified edge MUST raise, so a new graph edge
type can never render at the wrong trust level unnoticed.

Edge **types** are graph schema, not library content (Constitution VI) — no placeholders needed.
"""

from __future__ import annotations

import pytest

from chronovista.models.graph_connection import EdgeLayer, edge_layer_for

# (rel_type, rel_layer) → expected EdgeLayer. Covers every edge class observed in the prod
# graph census (2026-11-20): wikidata KB types, reviewed relationships, reviewed coincidence,
# category, and all co-occurrence channels.
_CASES: list[tuple[str, str | None, EdgeLayer]] = [
    # KB facts (layer='wikidata') → VERIFIED (sample across the ~24 types)
    ("MEMBER_OF", "wikidata", EdgeLayer.VERIFIED),
    ("EDUCATED_AT", "wikidata", EdgeLayer.VERIFIED),
    ("AWARD_RECEIVED", "wikidata", EdgeLayer.VERIFIED),
    ("POSITION_HELD", "wikidata", EdgeLayer.VERIFIED),
    ("PLACE_OF_BIRTH", "wikidata", EdgeLayer.VERIFIED),
    ("FOUNDER", "wikidata", EdgeLayer.VERIFIED),
    ("SPOUSE", "wikidata", EdgeLayer.VERIFIED),
    # human-reviewed RELATIONSHIPS (layer='reviewed') → VERIFIED
    ("ASSOCIATED_WITH", "reviewed", EdgeLayer.VERIFIED),
    ("COVERS", "reviewed", EdgeLayer.VERIFIED),
    ("CO_CAST", "reviewed", EdgeLayer.VERIFIED),
    # category membership → CATEGORY
    ("IN_CATEGORY", None, EdgeLayer.CATEGORY),
    # co-occurrence channels → CO_OCCURRENCE
    ("CO_OCCURS_TRANSCRIPT", None, EdgeLayer.CO_OCCURRENCE),
    ("CO_OCCURS_TITLEDESC", None, EdgeLayer.CO_OCCURRENCE),
    ("CO_OCCURS_TAGS", None, EdgeLayer.CO_OCCURRENCE),
    ("CO_OCCURS_MANUAL", None, EdgeLayer.CO_OCCURRENCE),
    # human "merely co-occur" verdict → CO_OCCURRENCE (the weak layer, not VERIFIED)
    ("REVIEWED_COINCIDENCE", "reviewed", EdgeLayer.CO_OCCURRENCE),
]


@pytest.mark.parametrize(("rel_type", "rel_layer", "expected"), _CASES)
def test_edge_layer_for_classifies_every_known_class(
    rel_type: str, rel_layer: str | None, expected: EdgeLayer
) -> None:
    assert edge_layer_for(rel_type, rel_layer) is expected


def test_reviewed_coincidence_is_not_verified() -> None:
    # The sharpest mutation target: REVIEWED_COINCIDENCE shares layer='reviewed' with the
    # reviewed relationships, but must NOT read as a verified fact.
    assert edge_layer_for("REVIEWED_COINCIDENCE", "reviewed") is EdgeLayer.CO_OCCURRENCE


@pytest.mark.parametrize(
    ("rel_type", "rel_layer"),
    [("TOTALLY_NEW_TYPE", None), ("SOMETHING", "unrecognized_layer"), ("", None)],
)
def test_unclassified_edge_raises_no_silent_unknown(
    rel_type: str, rel_layer: str | None
) -> None:
    with pytest.raises(ValueError):
        edge_layer_for(rel_type, rel_layer)
