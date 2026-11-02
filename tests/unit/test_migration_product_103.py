"""Feature 103 migration ``b4d8f2a6c0e1`` is internally correct (test-suite review G4).

The integration DB is built from the models via ``create_all``, so the migration's OWN SQL is
never exercised there — a typo (wrong column, wrong ``include_tag_only``, a missing constraint, or
a downgrade that is not a true inverse) could ship green. This reads the migration module directly
and pins its contract against the single source. No DB and no Alembic run required.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from chronovista.models.enums import entity_type_in_clause

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "src/chronovista/db/migrations/versions/b4d8f2a6c0e1_product_entity_type_103.py"
)

# (name, table, column, include_tag_only) — the canonical, intended mapping. A migration that
# swapped a column or dropped the candidate_suggestions constraint (the migration-051 trap) fails.
_EXPECTED = {
    ("chk_entity_type_valid", "named_entities", "entity_type", False),
    ("chk_canonical_tag_entity_type_valid", "canonical_tags", "entity_type", True),
    ("chk_candidate_type_hint_valid", "candidate_suggestions", "type_hint", False),
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mig_b4d8f2a6c0e1", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain() -> None:
    m = _load()
    assert m.revision == "b4d8f2a6c0e1"
    assert m.down_revision == "f1a7c3e9b2d4"


def test_covers_all_three_constraints_with_correct_mapping() -> None:
    """All three CHECKs — including chk_candidate_type_hint_valid that migration 051 missed."""
    m = _load()
    assert set(m._CONSTRAINTS) == _EXPECTED


def test_upgrade_sql_is_product_inclusive_from_single_source() -> None:
    """Each constraint's upgrade SQL is rendered from entity_type_in_clause and now includes product."""
    m = _load()
    for _name, _table, column, include_tag_only in m._CONSTRAINTS:
        rendered = entity_type_in_clause(column, include_tag_only=include_tag_only)
        assert "'product'" in rendered


def test_downgrade_is_a_true_inverse_without_product() -> None:
    """The downgrade lists are exactly the current vocabulary minus 'product' (a real inverse)."""
    m = _load()
    assert "'product'" not in m._OLD_PRODUCING
    assert "'product'" not in m._OLD_TAG_INCLUSIVE
    # Structural: tag-inclusive = producing + the two tag-only values.
    assert m._OLD_TAG_INCLUSIVE == m._OLD_PRODUCING + ", 'topic', 'descriptor'"
    # The 103 downgrade baseline is the FIXED pre-product vocabulary — independent of any type
    # added LATER (e.g. `law` in 104), so it is pinned to literals, never derived from the live
    # (ever-growing) tuple.
    pre_product = {
        "person",
        "organization",
        "place",
        "event",
        "work",
        "technical_term",
        "concept",
        "other",
    }
    old_values = {v.strip().strip("'") for v in m._OLD_PRODUCING.split(",")}
    assert old_values == pre_product
    assert {v.strip().strip("'") for v in m._OLD_TAG_INCLUSIVE.split(",")} == (
        pre_product | {"topic", "descriptor"}
    )
