"""Architecture fitness test — the determinate-classification predicate has one home.

Pilot application of the Constitution's Enforcement-Tiers rule (Anti-Slop → "Single-Source
Operations and Fitness Guards"): name a shared operation, give it one home, and guard the
single-source invariant with a one-line exact-count fitness test that CI runs on every push —
promoting the invariant from the Judgment tier (a reviewer *might* notice the duplication) to
the Automated tier (CI *will*).

Context: two backfill scripts (``backfill_candidate_types.py``, ``backfill_entity_types.py``)
each re-rolled "classify this P31, treat the catch-all OTHER as 'leave unchanged'" by calling
``classify_entity_type(...).value`` and comparing against a locally-redeclared
``_OTHER = "other"`` literal. Per-branch review never flagged it because each script was
internally correct — the duplication existed only *across* files. That is the small, verified
instance of the cross-branch accretion that Feature 101 addresses at scale, and this is the
rule piloted here before Feature 101 is built under it.

CAVEAT (honest): these are name/literal-based guards. They catch **honest duplication, not
deliberate evasion** — re-rolling the comparison against ``EntityType.OTHER`` directly (with no
``_OTHER`` literal) would pass. The goal is a reviewable diff that reads "this adds a second
place that decides type-determinacy", not a security boundary.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCAN_DIRS = (_REPO_ROOT / "src" / "chronovista", _REPO_ROOT / "scripts")


def _py_files() -> Iterator[Path]:
    for base in _SCAN_DIRS:
        for path in base.rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def test_classify_if_determinate_defined_exactly_once() -> None:
    """One home: the determinate predicate is defined in exactly one module."""
    pattern = re.compile(r"^def classify_if_determinate\b", re.MULTILINE)
    homes = [
        str(path.relative_to(_REPO_ROOT))
        for path in _py_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert len(homes) == 1, (
        "The determinate-classification predicate must have exactly one definition "
        f"(classify_if_determinate); found {len(homes)}: {homes}"
    )


def test_other_sentinel_is_never_redeclared() -> None:
    """No caller re-rolls the OTHER comparison with a magic ``_OTHER = "other"`` literal.

    Exact-count (zero) rather than a growable allowlist: adding a bypass means editing this
    assertion — a reviewable diff that reads "this adds a second place that decides determinacy".
    """
    pattern = re.compile(r'^_OTHER\s*=\s*["\']other["\']', re.MULTILINE)
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in _py_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "A module redeclared the OTHER sentinel to hand-roll the determinate-type comparison "
        "instead of calling classify_if_determinate(); offenders: "
        + ", ".join(offenders)
    )
