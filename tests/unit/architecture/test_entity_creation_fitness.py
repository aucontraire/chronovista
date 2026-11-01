"""Architecture fitness tests — entity creation has one home (Feature 101, FR-008).

Promotes the single-entry-point invariant from the Constitution's Judgment tier to the Automated
tier — the v1.3.0 "Single-Source Operations and Fitness Guards" rule, piloted by the taxonomy
predicate guard in ``test_taxonomy_predicate_fitness.py``. Three guards, each an exact-count
assertion over source text, run as ordinary unit tests on every push:

- **F-INSERT**: an entity row is inserted only via the uniquely-named
  ``NamedEntityRepository.insert_new_entity`` — it appears exactly twice (its definition + the
  single call in the shared core). The inherited generic ``create`` matches ~60 unrelated sites
  and is deliberately NOT the target (that is why FR-001 coined a unique insert name).
- **F-GROUND**: a grounding dict is built only via ``build_grounding`` — zero hand-built dict
  literals at the two ``external_ids`` entry seams (``external_ids={...}`` at creation, and
  ``add_external_id(identifier={...})`` at the JSONB merge).
- **F-ENRICH**: the enrichment-trigger helper ``schedule_enrichment`` is defined exactly once.

CAVEAT (stated honestly, per the amendment): these are name/literal-based guards. They catch
**honest duplication** — a new site that inserts an entity the ordinary way, hand-builds a
grounding dict the ordinary way, or defines a second trigger — **not deliberate evasion**
(aliasing the method, or building the dict in a differently-named variable then assigning it).
The goal is a reviewable diff that reads "this adds a second place that creates an entity",
not a security boundary.
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


def _hits(pattern: re.Pattern[str]) -> list[tuple[str, int]]:
    """Return ``(relative_path, match_count)`` for every scanned file with >= 1 match."""
    found: list[tuple[str, int]] = []
    for path in _py_files():
        n = len(pattern.findall(path.read_text(encoding="utf-8")))
        if n:
            found.append((str(path.relative_to(_REPO_ROOT)), n))
    return found


def test_f_insert_entity_inserted_only_via_core() -> None:
    """F-INSERT: ``insert_new_entity(`` appears exactly twice — its definition and the single
    call in ``services/entity_creation.py``. A third occurrence is a new insert site."""
    pattern = re.compile(r"\binsert_new_entity\(")
    hits = _hits(pattern)
    total = sum(n for _, n in hits)
    assert total == 2, (
        "An entity row must be inserted only through the shared core. `insert_new_entity(` must "
        f"appear exactly twice (its definition + the core's single call); found {total}: {hits}"
    )


def test_f_ground_dict_built_only_via_helper() -> None:
    """F-GROUND: no hand-built grounding dict literal at either ``external_ids`` entry seam.

    A content dict-literal assigned to ``external_ids=`` (creation) or passed as
    ``add_external_id(identifier=...)`` (the JSONB merge) bypasses the sole constructor
    ``build_grounding``. An empty ``{}`` and a ``build_grounding(...)``/variable value are fine.
    Bounded prohibition, not a growable allowlist — adding a bypass means editing this assertion.
    """
    pattern = re.compile(r"(?:external_ids|identifier)\s*=\s*\{\s*['\"]")
    offenders = _hits(pattern)
    assert offenders == [], (
        "A grounding dict was hand-built outside build_grounding at an external_ids seam "
        "(external_ids={...} at creation, or add_external_id(identifier={...}) at merge); "
        f"offenders: {offenders}"
    )


def test_f_enrich_trigger_defined_exactly_once() -> None:
    """F-ENRICH: the enrichment-trigger helper is defined in exactly one module."""
    pattern = re.compile(r"^def schedule_enrichment\b", re.MULTILINE)
    homes = [
        str(path.relative_to(_REPO_ROOT))
        for path in _py_files()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert len(homes) == 1, (
        "The enrichment-trigger helper must have exactly one definition (schedule_enrichment); "
        f"found {len(homes)}: {homes}"
    )
