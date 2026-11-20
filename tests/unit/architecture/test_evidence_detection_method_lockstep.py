"""Fitness guard: the ``DetectionMethod`` Literal and the ``entity_mentions.detection_method`` DB
CHECK stay in lockstep (a two-home contract).

The evidence models type ``detection_method`` as a strict ``Literal`` so a drifted value fails at the
serialization boundary. But the DB CHECK constraint is the source of truth for which values can
actually appear in a row. If the two drift apart, either a valid DB value 500s the whole evidence
page (Literal too narrow) or the Literal promises clients a value the DB forbids (too wide). They
must stay equal.

Mutation-verify (before merge): add or remove a value from the Literal (or from the CHECK) → this
guard goes red.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from chronovista.models.connection_evidence import DetectionMethod

_REPO = Path(__file__).resolve().parents[3]
_MODELS = _REPO / "src" / "chronovista" / "db" / "models.py"


def _db_check_values() -> set[str]:
    src = _MODELS.read_text()
    match = re.search(r"detection_method IN \(([^)]*)\)", src)
    assert match, "could not find the detection_method CHECK constraint in db/models.py"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_detection_method_literal_matches_db_check() -> None:
    literal_values = set(get_args(DetectionMethod))
    db_values = _db_check_values()
    assert literal_values == db_values, (
        "DetectionMethod Literal and the entity_mentions.detection_method DB CHECK have drifted. "
        f"Literal-only: {literal_values - db_values}; DB-only: {db_values - literal_values}. "
        "Update both so the evidence models never 500 on a valid DB value nor promise a forbidden one."
    )
